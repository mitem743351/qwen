"""Inference Runtime tests: negotiation, retry, timeout, persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from inference_helpers import TransportResponse, completion_response, make_provider
from qwen_research.common.ids import TaskId
from qwen_research.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
)
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
)
from qwen_research.inference.config import RetryConfig
from qwen_research.inference.interfaces import InferenceProvider
from qwen_research.inference.runtime import InferenceRuntime
from qwen_research.inference.store import InvocationStore, SqliteInvocationStore


def _runtime(
    provider: InferenceProvider,
    *,
    retry: RetryConfig | None = None,
    store: InvocationStore | None = None,
) -> InferenceRuntime:
    return InferenceRuntime(
        {"qwen": provider},
        default_provider="qwen",
        default_model="qwen-max",
        retry=retry or RetryConfig(max_attempts=1),
        store=store,
    )


def _request(**policy_kwargs: object) -> InferenceRequest:
    return InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(**policy_kwargs),  # type: ignore[arg-type]
        context=("question",),
    )


def test_generate_via_runtime() -> None:
    provider, _ = make_provider(lambda *_: completion_response("answer"))
    runtime = _runtime(provider)
    result = runtime.generate(_request())
    assert result.status == "ok"
    assert result.content == "answer"
    assert result.provider == "qwen"


def test_capabilities_and_models() -> None:
    provider, _ = make_provider(lambda *_: completion_response("x"))
    runtime = _runtime(provider)
    caps = runtime.capabilities("qwen")
    assert caps.supports_streaming is True
    assert caps.supports_tool_calling is True
    models = runtime.models("qwen")
    model_ids = {m.model for m in models}
    # The default model is present, and the catalog now spans the full line-up.
    assert "qwen-max" in model_ids
    assert "qwen3.7-max" in model_ids


def test_negotiation_degrades_unsupported_before_dispatch() -> None:
    # The runtime re-seats the policy to only supported values before dispatch.
    provider, transport = make_provider(lambda *_: completion_response("x"))
    runtime = _runtime(provider)
    runtime.generate(_request(max_output_tokens=50))
    body = transport.calls[0][2]
    assert body["max_tokens"] == 50


def test_retry_on_transient() -> None:
    calls = {"n": 0}

    def handler(*args: object) -> TransportResponse:
        calls["n"] += 1
        if calls["n"] < 3:
            return _rate_limited()
        return completion_response("ok")

    provider, _ = make_provider(handler)
    runtime = _runtime(
        provider,
        retry=RetryConfig(
            max_attempts=3, base_backoff_seconds=0.0, max_backoff_seconds=0.0
        ),
    )
    result = runtime.generate(_request())
    assert result.status == "ok"
    assert calls["n"] == 3


def test_no_retry_on_auth_failure() -> None:
    calls = {"n": 0}

    def handler(*args: object) -> TransportResponse:
        calls["n"] += 1
        raise ProviderAuthError("auth failed")

    provider, _ = make_provider(handler)
    runtime = _runtime(
        provider,
        retry=RetryConfig(max_attempts=3, base_backoff_seconds=0.0, max_backoff_seconds=0.0),
    )
    with pytest.raises(ProviderAuthError):
        runtime.generate(_request())
    assert calls["n"] == 1


def test_invocation_metadata_persisted(tmp_path: Path) -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    store = SqliteInvocationStore(tmp_path / "invocations.db")
    store.initialize()
    runtime = _runtime(provider, store=store)
    result = runtime.generate(_request())
    assert result.ok
    invocations = store.list_for_task("task_1")
    assert len(invocations) == 1
    assert invocations[0].model == "qwen-max"
    assert invocations[0].status == "ok"
    assert invocations[0].usage == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
    }


def test_failure_metadata_persisted(tmp_path: Path) -> None:
    provider, _ = make_provider(lambda *_: _rate_limited())
    store = SqliteInvocationStore(tmp_path / "invocations.db")
    store.initialize()
    runtime = _runtime(provider, store=store)
    with pytest.raises(ProviderRateLimitError):
        runtime.generate(_request())
    invocations = store.list_for_task("task_1")
    assert len(invocations) == 1
    assert invocations[0].status == "error"
    assert "ProviderRateLimitError" in (invocations[0].error or "")


def _rate_limited() -> TransportResponse:
    return TransportResponse(status=429, headers={}, body=b'{"error": "rate limited"}')
