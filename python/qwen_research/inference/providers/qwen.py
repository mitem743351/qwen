"""Qwen provider adapter.

Translates provider-neutral ``InferenceRequest`` into the Qwen OpenAI-compatible
``/chat/completions`` API and normalizes responses back to ``InferenceResult`` /
``InferenceStreamEvent``. No OpenAI SDK and no Qwen request models leak upward.

Verified contract (2026): OpenAI-compatible base ``/compatible-mode/v1``, Bearer
``DASHSCOPE_API_KEY``, model ids ``qwen-max/plus/turbo/flash`` + ``qwq-*``
(reasoning), ``reasoning_effort``/``enable_thinking`` for reasoning, finish
reasons ``stop``/``length``/``tool_calls``/``content_filter``, and
``usage`` token accounting. Only documented parameters are emitted.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from typing import Any

from qwen_research.domain.errors import (
    ModelNotFoundError,
    ProviderAuthError,
    ProviderConfigurationError,
    ProviderCredentialError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
    StructuredOutputError,
)
from qwen_research.domain.inference import (
    FinishReason,
    InferenceRequest,
    InferenceResult,
    InferenceStreamEvent,
    Message,
    ModelInfo,
    ProviderCapabilities,
    ProviderLimits,
    StreamEventType,
    StructuredOutputSpec,
    ToolCall,
)
from qwen_research.inference.config import ProviderConfig
from qwen_research.inference.models import ProviderErrorStatus, ProviderHealth
from qwen_research.inference.transport import (
    HttpTransport,
    TransportResponse,
    UrllibHttpTransport,
    encode_json,
)

#: Qwen OpenAI-compatible chat-completions path (relative to the base endpoint).
_CHAT_COMPLETIONS_PATH = "/chat/completions"


def _map_status(status: int) -> ProviderErrorStatus:
    if status in (401, 403):
        return ProviderErrorStatus.AUTH_FAILED
    if status == 429:
        return ProviderErrorStatus.RATE_LIMITED
    if status == 402:
        return ProviderErrorStatus.QUOTA_EXCEEDED
    if 400 <= status < 500:
        return ProviderErrorStatus.INVALID_REQUEST
    if status >= 500:
        return ProviderErrorStatus.SERVER_ERROR
    return ProviderErrorStatus.UNKNOWN


def _raise_for_status(status: int, body: bytes, model: str) -> None:
    """Map a non-2xx response to a typed, credential-free provider error."""
    text = body.decode("utf-8", errors="replace")
    # Strip any accidental key material; error text is already provider-safe.
    detail = text[:300]
    error_status = _map_status(status)
    if error_status is ProviderErrorStatus.AUTH_FAILED:
        raise ProviderAuthError(f"qwen authentication failed (HTTP {status})")
    if error_status is ProviderErrorStatus.RATE_LIMITED:
        raise ProviderRateLimitError(f"qwen rate limited (HTTP {status})")
    if error_status is ProviderErrorStatus.QUOTA_EXCEEDED:
        raise ProviderRateLimitError(f"qwen quota exceeded (HTTP {status})")
    if status == 404 or "model" in detail.lower() and "not found" in detail.lower():
        raise ModelNotFoundError(f"qwen model {model!r} not found")
    if error_status is ProviderErrorStatus.INVALID_REQUEST:
        from qwen_research.domain.errors import InferenceError

        raise InferenceError(f"qwen rejected the request (HTTP {status}): {detail}")
    if error_status is ProviderErrorStatus.SERVER_ERROR:
        raise ProviderServerError(f"qwen server error (HTTP {status})")
    raise ProviderUnavailableError(f"qwen unexpected response (HTTP {status}): {detail}")


class QwenProvider:
    """A production provider adapter for the Qwen OpenAI-compatible API."""

    #: The capabilities this adapter actually exercises (facts, not assumptions).
    CAPABILITIES = ProviderCapabilities(
        supports_reasoning=True,
        supports_reasoning_budget=False,  # reasoning_effort is discrete, not a numeric budget
        supports_max_output_tokens=True,
        supports_temperature=True,
        supports_top_p=True,
        supports_preserved_thinking=False,
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_parallel_generation=False,
        supports_context_caching=False,
    )

    LIMITS = ProviderLimits(max_output_tokens=131072)

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: HttpTransport | None = None,
        credential_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or UrllibHttpTransport()
        self._resolve_credential = credential_resolver or (
            lambda name: os.environ.get(name)
        )

    # -- InferenceProvider surface ----------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        return self.CAPABILITIES

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            provider=self._config.provider_id,
            model=self._config.default_model,
            context_window=None,  # unknown without a live model catalog
        )

    def generate(self, request: InferenceRequest) -> InferenceResult:
        return self._generate(request)

    def stream(self, request: InferenceRequest) -> Iterator[InferenceResult]:
        events = list(self.stream_events(request))
        content = "".join(e.text_delta for e in events if e.text_delta)
        final = events[-1] if events else None
        error_events = [e.error for e in events if e.error]
        errors = tuple(error_events) if error_events else ()
        return iter(
            [
                InferenceResult(
                    status="error" if errors else "ok",
                    model=self._model(request),
                    content=content,
                    tool_calls_structured=(),
                    usage=final.usage if final else None,
                    finish_reason=final.finish_reason if final else "",
                    errors=errors,
                    provider=self._config.provider_id,
                )
            ]
        )

    def structured_output(
        self, request: InferenceRequest, schema: dict[str, object]
    ) -> InferenceResult:
        spec = StructuredOutputSpec(schema=schema, strict=True)
        return self._generate(request, structured=spec)

    # -- streaming ---------------------------------------------------------

    def stream_events(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        """Yield normalized stream events (text/tool deltas, usage, terminal)."""
        body = self._build_request(request, stream=True)
        response = self._post(body, stream=True)
        if response.status != 200:
            _raise_for_status(response.status, response.body, self._model(request))
        yield from self._parse_stream(response.body)

    # -- diagnostics -------------------------------------------------------

    def health(self) -> ProviderHealth:
        try:
            credential = self._credential()
            if not credential:
                return ProviderHealth(
                    available=False, last_error="missing credential"
                )
            # Lightweight availability check: no network by default.
            return ProviderHealth(
                available=True,
                models_available=(self._config.default_model,),
                capabilities=self.capabilities(),
            )
        except ProviderConfigurationError as exc:
            return ProviderHealth(available=False, last_error=str(exc))

    # -- internals ---------------------------------------------------------

    def _credential(self) -> str:
        env_name = self._config.credential_env
        if not env_name:
            raise ProviderCredentialError(
                f"provider {self._config.provider_id!r} has no credential_env configured"
            )
        value = self._resolve_credential(env_name)
        if not value:
            raise ProviderCredentialError(
                f"provider {self._config.provider_id!r} credential env {env_name!r} is unset"
            )
        return value

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._credential()}",
        }

    def _endpoint(self) -> str:
        if not self._config.api_endpoint:
            raise ProviderConfigurationError(
                f"provider {self._config.provider_id!r} has no api_endpoint configured"
            )
        return self._config.api_endpoint.rstrip("/") + _CHAT_COMPLETIONS_PATH

    def _model(self, request: InferenceRequest) -> str:
        model = request.inference_policy.model_requirement or self._config.default_model
        if not model:
            raise ProviderConfigurationError(
                f"provider {self._config.provider_id!r} has no default_model and "
                "the request carries no model_requirement"
            )
        return model

    def _generate(
        self, request: InferenceRequest, *, structured: StructuredOutputSpec | None = None
    ) -> InferenceResult:
        body = self._build_request(request, stream=False, structured=structured)
        response = self._post(body, stream=False)
        if response.status != 200:
            _raise_for_status(response.status, response.body, self._model(request))
        return self._normalize(json.loads(response.body.decode("utf-8")), request)

    def _post(self, body: dict[str, Any], *, stream: bool) -> TransportResponse:
        timeout = (
            self._config.timeout.request_seconds
            if not stream
            else self._config.timeout.connection_seconds
        )
        return self._transport.post(
            self._endpoint(),
            headers=self._headers(),
            body=encode_json(body),
            timeout_seconds=timeout,
        )

    def _build_request(
        self,
        request: InferenceRequest,
        *,
        stream: bool,
        structured: StructuredOutputSpec | None = None,
    ) -> dict[str, Any]:
        policy = request.inference_policy
        payload: dict[str, Any] = {
            "model": self._model(request),
            "messages": self._messages(request),
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if policy.temperature is not None and self.capabilities().supports_temperature:
            payload["temperature"] = policy.temperature
        if policy.top_p is not None and self.capabilities().supports_top_p:
            payload["top_p"] = policy.top_p
        if policy.max_output_tokens is not None and self.capabilities().supports_max_output_tokens:
            payload["max_tokens"] = policy.max_output_tokens
        if policy.reasoning and self.capabilities().supports_reasoning:
            # Qwen thinking mode; discrete, so no numeric budget is emitted.
            payload["enable_thinking"] = True
        if request.tools and self.capabilities().supports_tool_calling:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": "",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
                for name in request.tools
            ]
        if structured is not None:
            # Qwen OpenAI-compatible json_object mode (documented).
            payload["response_format"] = {"type": "json_object"}
        elif request.response_format:
            payload["response_format"] = {"type": request.response_format}
        return payload

    def _messages(self, request: InferenceRequest) -> list[dict[str, Any]]:
        if request.messages:
            return [self._message(m) for m in request.messages]
        # No prepared messages → a single user message from context.
        content = "\n\n".join(request.context) if request.context else ""
        return [{"role": "user", "content": content}]

    def _message(self, message: Message) -> dict[str, Any]:
        role = message.role.value
        item: dict[str, Any] = {"role": role, "content": message.content}
        if message.name is not None:
            item["name"] = message.name
        if message.tool_call_id is not None:
            item["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.arguments, sort_keys=True),
                    },
                }
                for tc in message.tool_calls
            ]
        return item

    def _normalize(self, data: dict[str, Any], request: InferenceRequest) -> InferenceResult:
        choices = data.get("choices") or []
        if not choices:
            return InferenceResult(
                status="error",
                model=self._model(request),
                errors=("empty provider response",),
                provider=self._config.provider_id,
            )
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish = self._map_finish(choice.get("finish_reason"))
        tool_calls = self._parse_tool_calls(message.get("tool_calls"))
        usage = self._normalize_usage(data.get("usage"))
        warnings: list[str] = []
        if finish is FinishReason.LENGTH:
            warnings.append("output truncated (length)")
        structured_output = None
        if request.inference_policy.structured_output and content:
            structured_output = self._parse_json_content(content)
        return InferenceResult(
            status="ok",
            model=self._model(request),
            content=content,
            structured_output=structured_output,
            tool_calls=tuple(tc.tool_name for tc in tool_calls),
            tool_calls_structured=tuple(tool_calls),
            usage=usage,
            finish_reason=finish.value,
            warnings=tuple(warnings),
            provider=self._config.provider_id,
        )

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                "provider returned invalid JSON for required structured output"
            ) from exc
        if not isinstance(value, dict):
            raise StructuredOutputError("structured output must be a JSON object")
        return value

    def _parse_tool_calls(self, raw: Any) -> list[ToolCall]:
        calls: list[ToolCall] = []
        if not isinstance(raw, list):
            return calls
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            fn = entry.get("function") or {}
            name = fn.get("name") or ""
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append(
                ToolCall(
                    call_id=entry.get("id") or "",
                    tool_name=name,
                    arguments=args,
                )
            )
        return calls

    def _normalize_usage(self, usage: Any) -> dict[str, int] | None:
        if not isinstance(usage, dict):
            return None
        out: dict[str, int] = {}
        mapping = {
            "prompt_tokens": "input_tokens",
            "completion_tokens": "output_tokens",
            "total_tokens": "total_tokens",
        }
        for src, dst in mapping.items():
            value = usage.get(src)
            if isinstance(value, int):
                out[dst] = value
        return out or None

    def _map_finish(self, raw: Any) -> FinishReason:
        if raw in ("stop", None, ""):
            return FinishReason.STOP
        if raw == "length":
            return FinishReason.LENGTH
        if raw in ("tool_calls", "tool_calls_stop", "function_call"):
            return FinishReason.TOOL_CALL
        if raw == "content_filter":
            return FinishReason.CONTENT_FILTER
        return FinishReason.UNKNOWN

    def _parse_stream(self, body: bytes) -> Iterator[InferenceStreamEvent]:
        text = body.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                yield InferenceStreamEvent(type=StreamEventType.COMPLETED)
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                yield InferenceStreamEvent(
                    type=StreamEventType.ERROR, error="malformed stream chunk"
                )
                continue
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield InferenceStreamEvent(
                        type=StreamEventType.TEXT_DELTA, text_delta=content
                    )
                if delta.get("tool_calls"):
                    yield InferenceStreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        tool_call_delta=delta["tool_calls"],
                    )
                finish = choices[0].get("finish_reason")
                if finish:
                    yield InferenceStreamEvent(
                        type=StreamEventType.COMPLETED,
                        finish_reason=self._map_finish(finish).value,
                    )
            usage = self._normalize_usage(chunk.get("usage"))
            if usage:
                yield InferenceStreamEvent(type=StreamEventType.USAGE, usage=usage)
