"""Opt-in live Qwen smoke tests (never required for CI).

Run with a real credential:

    QWEN_LIVE_TEST=1 DASHSCOPE_API_KEY=... pytest tests/inference/test_live.py

Skipped unless ``QWEN_LIVE_TEST=1`` is set, so normal validation never requires
live credentials. Credentials are never logged. The ``qwen3.8-max-preview``
test is additionally gated on ``QWEN_LIVE_TOKEN_PLAN=1`` (it requires the
Token Plan endpoint/credential, which is configured separately).
"""

from __future__ import annotations

import os

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    ToolSpec,
)
from qwen_research.inference.config import DEFAULT_QWEN_PROVIDER, ProviderConfig
from qwen_research.inference.providers.qwen import QwenProvider
from qwen_research.inference.runtime import InferenceRuntime

pytestmark = pytest.mark.skipif(
    os.environ.get("QWEN_LIVE_TEST") != "1",
    reason="set QWEN_LIVE_TEST=1 and DASHSCOPE_API_KEY to run the live smoke test",
)


def _config(model: str, *, plan: str = "") -> ProviderConfig:
    return ProviderConfig(
        provider_id="qwen",
        api_endpoint=os.environ.get(
            "QWEN_RESEARCH_INFERENCE_ENDPOINT", DEFAULT_QWEN_PROVIDER.api_endpoint
        ),
        credential_env=os.environ.get(
            "QWEN_RESEARCH_INFERENCE_CREDENTIAL_ENV",
            DEFAULT_QWEN_PROVIDER.credential_env,
        ),
        default_model=model,
        plan=plan,
        endpoint_profile=os.environ.get("QWEN_RESEARCH_INFERENCE_ENDPOINT_PROFILE", ""),
    )


def test_live_single_generation() -> None:
    config = _config(os.environ.get("QWEN_RESEARCH_INFERENCE_MODEL", "qwen3.7-max"))
    provider = QwenProvider(config)
    runtime = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model=config.default_model
    )
    request = InferenceRequest(
        task_reference=TaskId("task_live"),
        inference_policy=InferencePolicy(max_output_tokens=64),
        context=("Say 'hello' in one word.",),
    )
    result = runtime.generate(request)
    assert result.ok, result.errors
    assert result.content
    assert result.finish_reason == "stop"
    assert result.usage is not None


@pytest.mark.skipif(
    os.environ.get("QWEN_LIVE_TOKEN_PLAN") != "1",
    reason="set QWEN_LIVE_TOKEN_PLAN=1 (Token Plan endpoint) to test qwen3.8-max-preview",
)
def test_live_qwen_38_preview_thinking_and_tools() -> None:
    """Live check for the Token-Plan-only preview (thinking + tool schema)."""
    config = _config("qwen3.8-max-preview", plan="token_plan")
    provider = QwenProvider(config)
    runtime = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model=config.default_model
    )
    request = InferenceRequest(
        task_reference=TaskId("task_live_preview"),
        inference_policy=InferencePolicy(reasoning=True, reasoning_budget=64, max_output_tokens=64),
        context=("Answer in one short sentence.",),
        tools=(ToolSpec(name="noop", description="placeholder", parameters={"type": "object"}),),
    )
    result = runtime.generate(request)
    assert result.ok, result.errors
    assert result.content
    assert result.usage is not None
