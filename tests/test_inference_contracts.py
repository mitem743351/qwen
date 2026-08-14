"""Inference contracts: capability representation and negotiation."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.domain.errors import InferenceError, ValidationError
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    ModelInfo,
    NegotiationDecision,
    NegotiationOutcome,
    ProviderCapabilities,
    negotiate,
)


def test_provider_capabilities_default_to_unsupported() -> None:
    caps = ProviderCapabilities()
    assert caps.supports_tool_calling is False
    assert caps.supports_structured_output is False


def test_policy_validation() -> None:
    with pytest.raises(ValidationError):
        InferencePolicy(max_output_tokens=-1)
    with pytest.raises(ValidationError):
        InferencePolicy(reasoning_budget=-1)
    with pytest.raises(ValidationError):
        InferencePolicy(temperature=-0.5)
    with pytest.raises(ValidationError):
        InferencePolicy(top_p=0.0)
    with pytest.raises(ValidationError):
        InferencePolicy(top_p=1.5)


def test_model_requirement_lives_only_on_policy() -> None:
    # InferenceRequest is a pure envelope; the policy is the single authority.
    policy = InferencePolicy(model_requirement="reasoning")
    request = InferenceRequest(task_reference=TaskId("task_1"), inference_policy=policy)
    assert request.inference_policy.model_requirement == "reasoning"
    # The request itself exposes no independent model requirement field.
    assert not hasattr(request, "model_requirement")


def test_request_and_result_contract() -> None:
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(),
    )
    assert request.task_reference == TaskId("task_1")
    result = InferenceResult(status="ok", model="qwen-xyz", content="answer")
    assert result.ok is True
    assert result.errors == ()


def test_negotiation_applies_supported() -> None:
    caps = ProviderCapabilities(supports_max_output_tokens=True, supports_tool_calling=True)
    policy = InferencePolicy(max_output_tokens=100, tool_calling=True)
    applied, decisions = negotiate(policy, caps)
    assert applied.max_output_tokens == 100
    assert applied.tool_calling is True
    assert all(d.outcome is NegotiationOutcome.APPLY for d in decisions)


def test_negotiation_degrades_unsupported() -> None:
    caps = ProviderCapabilities()  # nothing supported
    policy = InferencePolicy(max_output_tokens=100, temperature=0.7, top_p=0.9)
    applied, decisions = negotiate(policy, caps)
    assert applied.max_output_tokens is None
    assert applied.temperature is None
    assert applied.top_p is None
    assert {d.outcome for d in decisions} == {NegotiationOutcome.DEGRADE}


def test_negotiation_emulates_structured_output() -> None:
    caps = ProviderCapabilities(supports_structured_output=False)
    policy = InferencePolicy(structured_output=True)
    applied, decisions = negotiate(policy, caps)
    outcomes = {d.outcome for d in decisions}
    assert NegotiationOutcome.EMULATE in outcomes
    assert applied.structured_output is True


def test_negotiation_rejects_required_tool_calling() -> None:
    caps = ProviderCapabilities(supports_tool_calling=False)
    policy = InferencePolicy(tool_calling=True)
    with pytest.raises(InferenceError):
        negotiate(policy, caps)


def test_model_info() -> None:
    info = ModelInfo(provider="qwen", model="qwen-max", context_window=128000)
    assert info.context_window == 128000


def test_decision_is_typed_and_complete() -> None:
    caps = ProviderCapabilities()
    policy = InferencePolicy(max_output_tokens=50)
    _, decisions = negotiate(policy, caps)
    decision = decisions[0]
    assert isinstance(decision, NegotiationDecision)
    assert decision.element == "max_output_tokens"
    assert decision.requested is True
    assert decision.supported is False
    assert decision.outcome is NegotiationOutcome.DEGRADE
    assert decision.reason
    assert decision.effective_value is None
