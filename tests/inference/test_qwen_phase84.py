"""Phase 8.4: endpoint control, transient reasoning_content, context correction."""

from __future__ import annotations

import pytest

from inference_helpers import FakeQwenTransport, completion_response, make_provider
from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import dumps, loads
from qwen_research.domain.errors import InferenceError, ProviderConfigurationError
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    Message,
    MessageRole,
)
from qwen_research.inference.config import ProviderConfig
from qwen_research.inference.providers.qwen import QwenProvider
from qwen_research.inference.providers.qwen_availability import QwenEndpointProfile


def _request(**policy_kwargs: object) -> InferenceRequest:
    return InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(**policy_kwargs),  # type: ignore[arg-type]
        context=("question",),
    )


def _provider_with_endpoint(
    transport: FakeQwenTransport,
    *,
    endpoint_profile: str,
    api_endpoint: str = "",
    default_model: str = "qwen3.7-max",
) -> QwenProvider:
    return QwenProvider(
        ProviderConfig(
            provider_id="qwen",
            api_endpoint=api_endpoint,
            credential_env="TEST_QWEN_API_KEY",
            default_model=default_model,
            endpoint_profile=endpoint_profile,
        ),
        transport=transport,
        credential_resolver=lambda name: "test-key",
        endpoint_profiles={
            "custom": QwenEndpointProfile(
                endpoint_id="custom",
                base_url="https://custom.example.com/v1",
                model_allowlist=("qwen3.7-max",),
            ),
        },
    )


# -- requirement 1: endpoint profile controls/validates the network endpoint --


def test_endpoint_profile_controls_network_endpoint() -> None:
    transport = FakeQwenTransport(lambda *_: completion_response("ok"))
    provider = _provider_with_endpoint(transport, endpoint_profile="custom")
    provider.generate(_request())
    url = transport.calls[0][0]
    assert url == "https://custom.example.com/v1/chat/completions"


def test_endpoint_profile_conflict_raises() -> None:
    transport = FakeQwenTransport(lambda *_: completion_response("ok"))
    provider = _provider_with_endpoint(
        transport,
        endpoint_profile="custom",
        api_endpoint="https://other.example.com/v1",
    )
    with pytest.raises(ProviderConfigurationError):
        provider.generate(_request())


def test_endpoint_profile_matches_api_endpoint_is_ok() -> None:
    transport = FakeQwenTransport(lambda *_: completion_response("ok"))
    provider = _provider_with_endpoint(
        transport,
        endpoint_profile="custom",
        api_endpoint="https://custom.example.com/v1",
    )
    provider.generate(_request())
    assert transport.calls[0][0] == "https://custom.example.com/v1/chat/completions"


# -- requirement 2 & 5: transient reasoning_content for multi-turn continuation --


def test_reasoning_content_emitted_for_assistant_message() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(),
        messages=(
            Message(
                role=MessageRole.ASSISTANT,
                content="prior answer",
                reasoning_content="hidden CoT",
            ),
            Message(role=MessageRole.USER, content="follow up"),
        ),
    )
    provider.generate(request)
    body = transport.calls[0][2]
    assert body["messages"][0]["reasoning_content"] == "hidden CoT"
    # User messages never carry reasoning_content.
    assert "reasoning_content" not in body["messages"][1]


def test_preserve_thinking_missing_reasoning_raises() -> None:
    # qwen3.8-max-preview: thinking forced, preserve_thinking supported. A prior
    # assistant turn without reasoning_content would silently drop state.
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(
            model_requirement="qwen3.8-max-preview",
            preserved_thinking=True,
            reasoning=True,
        ),
        messages=(
            Message(role=MessageRole.ASSISTANT, content="prior answer"),
            Message(role=MessageRole.USER, content="follow up"),
        ),
    )
    with pytest.raises(InferenceError):
        provider.generate(request)


def test_preserve_thinking_permissive_for_hybrid_model() -> None:
    # qwen3.7-max is hybrid (not thinking-forced): a prior assistant turn
    # without reasoning_content is NOT treated as a silent drop.
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(
            model_requirement="qwen3.7-max",
            preserved_thinking=True,
            reasoning=True,
        ),
        messages=(
            Message(role=MessageRole.ASSISTANT, content="prior answer"),
            Message(role=MessageRole.USER, content="follow up"),
        ),
    )
    result = provider.generate(request)
    assert result.status == "ok"
    # reasoning_content is simply not present (carried as-is, no error).
    body = transport.calls[0][2]
    assert "reasoning_content" not in body["messages"][0]


def test_preserve_thinking_with_reasoning_content_is_ok() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(
            model_requirement="qwen3.8-max-preview",
            preserved_thinking=True,
            reasoning=True,
        ),
        messages=(
            Message(
                role=MessageRole.ASSISTANT,
                content="prior answer",
                reasoning_content="hidden CoT",
            ),
            Message(role=MessageRole.USER, content="follow up"),
        ),
    )
    result = provider.generate(request)
    assert result.status == "ok"
    body = transport.calls[0][2]
    assert body["messages"][0]["reasoning_content"] == "hidden CoT"
    assert body["preserve_thinking"] is True


def test_reasoning_content_is_transient_not_serialized() -> None:
    message = Message(
        role=MessageRole.ASSISTANT,
        content="answer",
        reasoning_content="hidden CoT",
    )
    restored = loads(dumps(message))
    assert restored.content == "answer"
    # The transient field is not persisted.
    assert restored.reasoning_content == ""


# -- requirement 6: reasoning_effort is cataloged but not executed --


def test_reasoning_effort_is_not_emitted() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    provider.generate(
        _request(model_requirement="qwen3.8-max-preview", reasoning=True)
    )
    body = transport.calls[0][2]
    assert "reasoning_effort" not in body
    # Thinking is still activated, but only via enable_thinking.
    assert body["enable_thinking"] is True


def test_reasoning_effort_levels_are_cataloged() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    spec = provider._resolve_spec("qwen3.8-max-preview")
    assert spec.reasoning_effort_levels == ("low", "medium", "xhigh")
    # Plain models do not catalog reasoning_effort.
    assert provider._resolve_spec("qwen3.7-max").reasoning_effort_levels == ()


def test_reasoning_effort_and_thinking_budget_are_exclusive() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    # A payload carrying both controls must be rejected for qwen3.8-max-preview.
    with pytest.raises(InferenceError):
        provider._enforce_thinking_control_exclusivity(
            "qwen3.8-max-preview",
            {"reasoning_effort": "xhigh", "thinking_budget": 500},
        )


def test_reasoning_effort_and_thinking_budget_exclusivity_is_model_aware() -> None:
    provider, _ = make_provider(lambda *_: completion_response("ok"))
    # A model without reasoning_effort has no exclusivity constraint.
    provider._enforce_thinking_control_exclusivity(
        "qwen3.7-max", {"thinking_budget": 500}
    )
    # And a normal request only emits thinking_budget (no reasoning_effort).
    provider2, transport = make_provider(lambda *_: completion_response("ok"))
    provider2.generate(
        _request(model_requirement="qwen3.8-max-preview", reasoning_budget=64)
    )
    body = transport.calls[0][2]
    assert body["thinking_budget"] == 64
    assert "reasoning_effort" not in body
