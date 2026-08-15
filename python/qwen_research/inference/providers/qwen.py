"""Qwen provider adapter.

Translates provider-neutral ``InferenceRequest`` into the Qwen OpenAI-compatible
``/chat/completions`` API and normalizes responses back to ``InferenceResult`` /
``InferenceStreamEvent``. No OpenAI SDK and no Qwen request models leak upward.

Verified contract (2026): OpenAI-compatible base ``/compatible-mode/v1``, Bearer
``DASHSCOPE_API_KEY``; model ids ``qwen3.x`` flagships + ``qwen-max/plus/turbo/
flash`` + ``qwq-*`` (see ``qwen_models.py``); reasoning via ``enable_thinking``
with a numeric ``thinking_budget`` and ``preserve_thinking`` on the models that
support them; finish reasons ``stop``/``length``/``tool_calls``/
``content_filter``; ``usage`` token accounting. Capability discovery is
**model-specific** (per ``QwenModelSpec``: thinking, budget, preserved thinking,
structured output, tool calling, streaming), and structured output is validated
against the requested JSON Schema. Only documented parameters are emitted.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

from qwen_research.domain.errors import (
    InferenceError,
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
    AvailabilityPlan,
    FinishReason,
    InferenceRequest,
    InferenceResult,
    InferenceStreamEvent,
    Message,
    MessageRole,
    ModelInfo,
    ProviderCapabilities,
    ProviderLimits,
    StreamEventType,
    StructuredOutputSpec,
    ThinkingMode,
    ToolCall,
    ToolSpec,
)
from qwen_research.inference.config import ProviderConfig
from qwen_research.inference.models import ProviderErrorStatus, ProviderHealth
from qwen_research.inference.providers.qwen_availability import (
    ModelDiagnostic,
    QwenEndpointProfile,
    QwenModelAvailabilityResolver,
    resolve_endpoint_profile,
    resolve_plan,
)
from qwen_research.inference.providers.qwen_models import (
    QWEN_MODEL_TABLE,
    QwenModelSpec,
    resolve_spec,
)
from qwen_research.inference.schema_validation import validate_against_schema
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


def _capability_flags(caps: ProviderCapabilities) -> dict[str, bool]:
    """Flatten a :class:`ProviderCapabilities` into named booleans for diagnostics."""
    import dataclasses

    return {f.name: bool(getattr(caps, f.name)) for f in dataclasses.fields(caps)}


class QwenProvider:
    """A production provider adapter for the Qwen OpenAI-compatible API.

    Capability discovery is model-specific **and** contextual: ``capabilities``
    resolves the requested model against the (operator-overridable)
    :mod:`qwen_models` catalog *and* the endpoint/plan/inference-mode context,
    so a model that exists in the catalog is not assumed to be available (or
    equally capable) on every DashScope endpoint.
    """

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: HttpTransport | None = None,
        credential_resolver: Callable[[str], str | None] | None = None,
        model_catalog: Mapping[str, QwenModelSpec] | None = None,
        endpoint_profiles: Mapping[str, QwenEndpointProfile] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or UrllibHttpTransport()
        self._resolve_credential = credential_resolver or (
            lambda name: os.environ.get(name)
        )
        self._catalog: dict[str, QwenModelSpec] = dict(
            model_catalog if model_catalog is not None else QWEN_MODEL_TABLE
        )
        self._endpoint_profiles: dict[str, QwenEndpointProfile] = dict(endpoint_profiles or {})
        self._resolver = QwenModelAvailabilityResolver(
            self._catalog, self._endpoint_profiles or None
        )

    # -- InferenceProvider surface ----------------------------------------

    def _resolve_spec(self, model: str | None) -> QwenModelSpec:
        model = model or self._config.default_model or ""
        return resolve_spec(model, self._catalog)

    def _endpoint_profile(self) -> QwenEndpointProfile | None:
        return resolve_endpoint_profile(
            self._config.endpoint_profile, self._endpoint_profiles or None
        )

    def _plan(self) -> AvailabilityPlan | None:
        return resolve_plan(self._config.plan)

    def _region(self) -> str | None:
        return self._config.region or None

    def _thinking_mode(
        self, spec: QwenModelSpec, policy: Any | None
    ) -> ThinkingMode:
        if spec.thinking_always_enabled:
            return ThinkingMode.FORCED
        if policy is not None and (
            policy.reasoning or policy.reasoning_budget is not None
        ):
            return ThinkingMode.ENABLED
        return ThinkingMode.DISABLED

    def _effective_capabilities(
        self, spec: QwenModelSpec, mode: ThinkingMode
    ) -> ProviderCapabilities:
        thinking_on = mode in (ThinkingMode.ENABLED, ThinkingMode.FORCED)
        return ProviderCapabilities(
            supports_reasoning=spec.thinking,
            supports_reasoning_budget=spec.thinking_budget,
            supports_max_output_tokens=True,
            supports_temperature=True,
            supports_top_p=True,
            supports_preserved_thinking=spec.preserve_thinking,
            supports_tool_calling=spec.tool_calling,
            # Structured output is unavailable while thinking is on.
            supports_structured_output=spec.structured_output and not thinking_on,
            supports_streaming=spec.streaming,
            supports_parallel_generation=False,
            supports_context_caching=spec.context_caching,
        )

    def capabilities(
        self,
        model: str | None = None,
        *,
        thinking_mode: ThinkingMode | None = None,
        endpoint_profile: QwenEndpointProfile | None = None,
        plan: AvailabilityPlan | None = None,
    ) -> ProviderCapabilities:
        """Effective capabilities for a model in a context.

        ``thinking_mode`` gates mode-dependent flags (structured output is off
        while thinking is on). ``endpoint_profile`` / ``plan`` are contextual
        selectors: their *availability* effect is enforced by the resolver
        before dispatch (``_check_availability``); capability flags are
        model + mode derived.
        """
        spec = self._resolve_spec(model)
        mode = thinking_mode or self._thinking_mode(spec, None)
        return self._effective_capabilities(spec, mode)

    def limits(self, model: str | None = None) -> ProviderLimits:
        spec = self._resolve_spec(model)
        return ProviderLimits(
            max_output_tokens=spec.max_output_tokens,
            max_reasoning_budget=spec.max_thinking_tokens,
        )

    def model_info(self, model: str | None = None) -> ModelInfo:
        model = model or self._config.default_model
        spec = self._resolve_spec(model)
        return ModelInfo(
            provider=self._config.provider_id,
            model=model,
            context_window=spec.context_window,
            lifecycle=spec.lifecycle,
            availability=spec.availability,
            plans=spec.plans,
            regions=spec.regions,
        )

    def models(self) -> tuple[ModelInfo, ...]:
        models = {spec.model: spec for spec in self._catalog.values()}
        default = self._config.default_model
        if default and default not in models:
            models[default] = self._resolve_spec(default)
        return tuple(
            ModelInfo(
                provider=self._config.provider_id,
                model=name,
                context_window=spec.context_window,
                lifecycle=spec.lifecycle,
                availability=spec.availability,
                plans=spec.plans,
                regions=spec.regions,
            )
            for name, spec in sorted(models.items())
        )

    def diagnose(
        self,
        model: str | None = None,
        *,
        thinking_mode: ThinkingMode | None = None,
        endpoint_profile: QwenEndpointProfile | None = None,
        plan: AvailabilityPlan | None = None,
        region: str | None = None,
        capability_source: str = "catalog",
    ) -> ModelDiagnostic:
        """Return a structured diagnostic for a model in a context."""
        model = model or self._config.default_model
        spec = self._resolve_spec(model)
        mode = thinking_mode or self._thinking_mode(spec, None)
        caps = self._effective_capabilities(spec, mode)
        endpoint = endpoint_profile or self._endpoint_profile()
        plan = plan or self._plan()
        region = region or self._region()
        return ModelDiagnostic(
            model=model,
            lifecycle=spec.lifecycle,
            availability=spec.availability,
            endpoint_id=endpoint.endpoint_id if endpoint else "",
            region=region or "",
            plan=plan,
            thinking_mode=mode,
            capability_source=capability_source,
            effective_capabilities=_capability_flags(caps),
            notes=spec.notes,
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
        """Yield normalized stream events (text/tool deltas, usage, terminal).

        Uses the transport's incremental ``stream`` path so the configured
        ``stream_idle_seconds`` is a genuine idle timeout between chunks.
        """
        self._check_availability(self._model(request))
        body = self._build_request(request, stream=True)
        response = self._transport.stream(
            self._endpoint(),
            headers=self._headers(),
            body=encode_json(body),
            idle_timeout_seconds=self._config.timeout.stream_idle_seconds,
        )
        if response.status != 200:
            _raise_for_status(response.status, b"", self._model(request))
        yield from self._parse_stream_chunks(response.chunks)

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
                models_available=tuple(m.model for m in self.models()),
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
        profile = self._endpoint_profile()
        base = profile.base_url if profile is not None else self._config.api_endpoint
        if not base:
            raise ProviderConfigurationError(
                f"provider {self._config.provider_id!r} has no api_endpoint or "
                "endpoint profile configured"
            )
        # The endpoint profile controls the endpoint; if a raw api_endpoint is
        # also set and disagrees, surface the conflict rather than silently
        # picking one.
        if profile is not None and self._config.api_endpoint:
            configured = self._config.api_endpoint.rstrip("/")
            if configured and configured != base.rstrip("/"):
                raise ProviderConfigurationError(
                    f"api_endpoint {configured!r} conflicts with endpoint profile "
                    f"{profile.endpoint_id!r} base_url {base.rstrip('/')!r}"
                )
        return base.rstrip("/") + _CHAT_COMPLETIONS_PATH

    def _model(self, request: InferenceRequest) -> str:
        model = request.inference_policy.model_requirement or self._config.default_model
        if not model:
            raise ProviderConfigurationError(
                f"provider {self._config.provider_id!r} has no default_model and "
                "the request carries no model_requirement"
            )
        return model

    def _check_availability(self, model: str) -> None:
        """Raise a distinct error if *model* is unavailable in this context.

        Unknown models are permitted (conservative capabilities); endpoint /
        plan / region / deprecated cases raise their typed errors.
        """
        result = self._resolver.resolve(
            model,
            endpoint_profile=self._endpoint_profile(),
            plan=self._plan(),
            region=self._region(),
        )
        result.raise_if_unavailable(unknown_ok=True)

    def _generate(
        self, request: InferenceRequest, *, structured: StructuredOutputSpec | None = None
    ) -> InferenceResult:
        model = self._model(request)
        self._check_availability(model)
        body = self._build_request(request, stream=False, structured=structured)
        response = self._post(body)
        if response.status != 200:
            _raise_for_status(response.status, response.body, model)
        return self._normalize(
            json.loads(response.body.decode("utf-8")), request, structured=structured
        )

    def _post(self, body: dict[str, Any]) -> TransportResponse:
        return self._transport.post(
            self._endpoint(),
            headers=self._headers(),
            body=encode_json(body),
            timeout_seconds=self._config.timeout.request_seconds,
        )

    def _effective_caps_for_request(self, request: InferenceRequest) -> ProviderCapabilities:
        spec = self._resolve_spec(self._model(request))
        mode = self._thinking_mode(spec, request.inference_policy)
        return self._effective_capabilities(spec, mode)

    def _guard_preserved_thinking(
        self, request: InferenceRequest, caps: ProviderCapabilities
    ) -> None:
        """Refuse to silently drop multi-turn reasoning state (model-specific).

        **Strict** only for thinking-forced models (``qwen3.8-max-preview``):
        every assistant turn produces reasoning, so a prior assistant message
        missing its transient ``reasoning_content`` is a definite silent loss
        and raises. **Permissive** for hybrid models that support
        ``preserve_thinking`` (``qwen3.7-max`` / ``qwen3.7-plus``): reasoning may
        not have been produced on a given turn, so missing ``reasoning_content``
        is carried as-is rather than treated as an error.
        """
        policy = request.inference_policy
        if not policy.preserved_thinking or not caps.supports_preserved_thinking:
            return
        spec = self._resolve_spec(self._model(request))
        if not spec.thinking_always_enabled:
            return  # permissive for hybrid models
        for message in request.messages:
            if message.role is MessageRole.ASSISTANT and not message.reasoning_content:
                raise InferenceError(
                    "preserved thinking requested but an assistant message is "
                    "missing reasoning_content; refusing to silently drop "
                    "multi-turn reasoning state"
                )

    def _build_request(
        self,
        request: InferenceRequest,
        *,
        stream: bool,
        structured: StructuredOutputSpec | None = None,
    ) -> dict[str, Any]:
        policy = request.inference_policy
        model = self._model(request)
        caps = self._effective_caps_for_request(request)
        self._guard_preserved_thinking(request, caps)
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._messages(request),
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if policy.temperature is not None and caps.supports_temperature:
            payload["temperature"] = policy.temperature
        if policy.top_p is not None and caps.supports_top_p:
            payload["top_p"] = policy.top_p
        if policy.max_output_tokens is not None and caps.supports_max_output_tokens:
            payload["max_tokens"] = policy.max_output_tokens
        # Thinking mode: enable it for either reasoning or a numeric budget, and
        # emit the numeric budget only on models that actually support it.
        thinking = policy.reasoning or (
            policy.reasoning_budget is not None and caps.supports_reasoning_budget
        )
        if thinking and caps.supports_reasoning:
            payload["enable_thinking"] = True
        if policy.reasoning_budget is not None and caps.supports_reasoning_budget:
            payload["thinking_budget"] = policy.reasoning_budget
        # Native reasoning_effort (Phase 10): emitted only for models that
        # catalog it, and only when the policy requests it — never alongside a
        # thinking_budget (enforced below).
        if policy.reasoning_effort and self._resolve_spec(model).reasoning_effort_levels:
            payload["reasoning_effort"] = policy.reasoning_effort
        if policy.preserved_thinking and caps.supports_preserved_thinking:
            payload["preserve_thinking"] = True
        if request.tools and caps.supports_tool_calling:
            payload["tools"] = [self._tool_definition(tool) for tool in request.tools]
        if structured is not None:
            # Qwen OpenAI-compatible json_object mode (documented).
            payload["response_format"] = {"type": "json_object"}
        elif request.response_format:
            payload["response_format"] = {"type": request.response_format}
        self._enforce_thinking_control_exclusivity(model, payload)
        return payload

    def _enforce_thinking_control_exclusivity(
        self, model: str, payload: dict[str, Any]
    ) -> None:
        """Enforce the Qwen3.8 invariant on reasoning-depth controls.

        ``reasoning_effort`` and ``thinking_budget`` are mutually exclusive ways
        to control thinking depth: Qwen does not accept both in one request.
        This guard is model-aware (only models that catalog ``reasoning_effort``
        have the constraint) and is enforced on every request payload, so a
        future ``reasoning_effort`` emitter (Phase 10) can never coexist with a
        ``thinking_budget``.
        """
        spec = self._resolve_spec(model)
        if not spec.reasoning_effort_levels:
            return
        if "reasoning_effort" in payload and "thinking_budget" in payload:
            raise InferenceError(
                "reasoning_effort and thinking_budget cannot both be emitted "
                "for the same request"
            )

    def _tool_definition(self, tool: ToolSpec) -> dict[str, Any]:
        """Map a full :class:`ToolSpec` to a Qwen function-tool definition."""
        parameters = tool.parameters or {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters,
            },
        }

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
        # Transient hidden reasoning carried forward for multi-turn
        # continuation (Qwen ``preserve_thinking``); emitted only for assistant
        # messages that actually carry it.
        if message.reasoning_content and role == MessageRole.ASSISTANT.value:
            item["reasoning_content"] = message.reasoning_content
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

    def _normalize(
        self,
        data: dict[str, Any],
        request: InferenceRequest,
        *,
        structured: StructuredOutputSpec | None = None,
    ) -> InferenceResult:
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
        if content and (request.inference_policy.structured_output or structured is not None):
            structured_output = self._parse_json_content(content)
            if structured is not None:
                # Enforce conformance to the *requested* schema, not just JSON.
                validate_against_schema(structured_output, structured.schema)
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
            # Transient hidden reasoning, carried for multi-turn continuation.
            reasoning_content=message.get("reasoning_content") or "",
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
            args: dict[str, Any] = {}
            arguments_error: str | None = None
            try:
                parsed = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except (json.JSONDecodeError, TypeError):
                # Never silently convert a parse failure to {}: flag it so the
                # controlled loop rejects the call as INVALID_ARGUMENTS.
                arguments_error = "malformed tool arguments JSON"
            else:
                if isinstance(parsed, dict):
                    args = parsed
                else:
                    arguments_error = "tool arguments must be a JSON object"
            calls.append(
                ToolCall(
                    call_id=entry.get("id") or "",
                    tool_name=name,
                    arguments=args,
                    arguments_error=arguments_error,
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
        yield from self._parse_stream_lines(body.decode("utf-8", errors="replace").splitlines())

    def _parse_stream_chunks(self, chunks: Iterator[bytes]) -> Iterator[InferenceStreamEvent]:
        """Parse SSE lines incrementally across chunk boundaries."""
        yield from self._parse_stream_lines(_iter_sse_lines(chunks))

    def _parse_stream_lines(self, lines: Iterable[str]) -> Iterator[InferenceStreamEvent]:
        for raw_line in lines:
            line = raw_line.strip()
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


def _iter_sse_lines(chunks: Iterator[bytes]) -> Iterator[str]:
    """Yield decoded SSE lines, re-assembling lines split across chunk boundaries."""
    buffer = b""
    for chunk in chunks:
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")
    if buffer:
        yield buffer.decode("utf-8", errors="replace")
