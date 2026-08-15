"""Opt-in live Qwen smoke test (never required for CI).

Run with a real credential:

    QWEN_LIVE_TEST=1 DASHSCOPE_API_KEY=... pytest tests/inference/test_live.py

It is skipped unless ``QWEN_LIVE_TEST=1`` is set, so normal validation never
requires live credentials. Credentials are never logged.
"""

from __future__ import annotations

import os

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import InferencePolicy, InferenceRequest
from qwen_research.inference.config import DEFAULT_QWEN_PROVIDER, ProviderConfig
from qwen_research.inference.providers.qwen import QwenProvider
from qwen_research.inference.runtime import InferenceRuntime

pytestmark = pytest.mark.skipif(
    os.environ.get("QWEN_LIVE_TEST") != "1",
    reason="set QWEN_LIVE_TEST=1 and DASHSCOPE_API_KEY to run the live smoke test",
)


def test_live_single_generation() -> None:
    config = ProviderConfig(
        provider_id="qwen",
        api_endpoint=os.environ.get(
            "QWEN_RESEARCH_INFERENCE_ENDPOINT", DEFAULT_QWEN_PROVIDER.api_endpoint
        ),
        credential_env=DEFAULT_QWEN_PROVIDER.credential_env,
        default_model=os.environ.get("QWEN_RESEARCH_INFERENCE_MODEL", "qwen3.7-max"),
    )
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
