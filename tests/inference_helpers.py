"""Helpers for Phase 8 inference tests (fake transport, no live API key)."""

from __future__ import annotations

import json
from collections.abc import Callable

from qwen_research.inference.config import ProviderConfig
from qwen_research.inference.providers.qwen import QwenProvider
from qwen_research.inference.transport import TransportResponse


class FakeQwenTransport:
    """A scriptable :class:`HttpTransport` that records requests.

    ``handler`` receives ``(url, headers, body_dict, timeout_seconds)`` and
    returns a :class:`TransportResponse` (or raises).
    """

    def __init__(
        self,
        handler: Callable[[str, dict, dict, float], TransportResponse],
    ) -> None:
        self._handler = handler
        self.calls: list[tuple[str, dict, dict, float]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        payload = json.loads(body.decode("utf-8"))
        self.calls.append((url, headers, payload, timeout_seconds))
        return self._handler(url, headers, payload, timeout_seconds)


def make_provider(
    handler: Callable[[str, dict, dict, float], TransportResponse],
    *,
    api_key: str = "test-key",
) -> tuple[QwenProvider, FakeQwenTransport]:
    transport = FakeQwenTransport(handler)
    config = ProviderConfig(
        provider_id="qwen",
        api_endpoint="https://example.invalid/compatible-mode/v1",
        credential_env="TEST_QWEN_API_KEY",
        default_model="qwen-max",
    )
    provider = QwenProvider(
        config,
        transport=transport,
        credential_resolver=lambda name: api_key if name == "TEST_QWEN_API_KEY" else None,
    )
    return provider, transport


def json_response(payload: dict, *, status: int = 200) -> TransportResponse:
    return TransportResponse(
        status=status,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def completion_response(
    content: str,
    *,
    finish_reason: str = "stop",
    usage: dict | None = None,
    tool_calls: list | None = None,
    model: str = "qwen-max",
) -> TransportResponse:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return json_response(
        {
            "choices": [{"finish_reason": finish_reason, "message": message}],
            "model": model,
            "usage": usage
            or {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
    )


def sse_response(*chunks: dict) -> TransportResponse:
    lines = []
    for chunk in chunks:
        lines.append("data: " + json.dumps(chunk))
    lines.append("data: [DONE]")
    return TransportResponse(
        status=200,
        headers={"content-type": "text/event-stream"},
        body=("\n".join(lines) + "\n\n").encode("utf-8"),
    )
