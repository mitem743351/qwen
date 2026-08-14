"""Phase 1.2 — native vs workflow-emulated capability semantics.

Proves that EMULATE never masquerades as a provider-supported parameter, that
the negotiated result separates the provider policy from the workflow emulation
plan, and that XHIGH does not pretend provider-native reasoning control exists.
"""

from __future__ import annotations

import pytest

from qwen_research.common.serialization import dumps, loads
from qwen_research.domain.errors import InferenceError
from qwen_research.domain.inference import (
    CapabilityClass,
    InferencePolicy,
    NegotiationOutcome,
    ProviderCapabilities,
    ProviderLimits,
    negotiate,
)
from qwen_research.domain.reasoning import XHIGH


def test_native_capability_applies() -> None:
    caps = ProviderCapabilities(supports_reasoning=True)
    policy = InferencePolicy(reasoning=True)
    result = negotiate(policy, caps)
    decision = result.decisions[0]
    assert decision.outcome is NegotiationOutcome.APPLY
    assert decision.capability_class is CapabilityClass.NATIVE
    assert result.provider_policy.reasoning is True


def test_supported_numeric_limit_applies() -> None:
    caps = ProviderCapabilities(supports_max_output_tokens=True)
    policy = InferencePolicy(max_output_tokens=8000)
    result = negotiate(policy, caps)
    decision = result.decisions[0]
    assert decision.outcome is NegotiationOutcome.APPLY
    assert result.provider_policy.max_output_tokens == 8000


def test_numeric_overage_degrades_to_lower_bound() -> None:
    caps = ProviderCapabilities(supports_max_output_tokens=True)
    limits = ProviderLimits(max_output_tokens=32000)
    policy = InferencePolicy(max_output_tokens=100000)
    result = negotiate(policy, caps, limits)
    decision = result.decisions[0]
    assert decision.outcome is NegotiationOutcome.DEGRADE
    assert decision.effective_value == 32000
    assert result.provider_policy.max_output_tokens == 32000


def test_workflow_emulatable_emulates() -> None:
    caps = ProviderCapabilities()  # nothing supported
    policy = InferencePolicy(reasoning=True)
    result = negotiate(policy, caps)
    decision = result.decisions[0]
    assert decision.outcome is NegotiationOutcome.EMULATE
    assert decision.capability_class is CapabilityClass.WORKFLOW_EMULATABLE


def test_emulated_capability_absent_from_provider_policy() -> None:
    caps = ProviderCapabilities()  # nothing supported
    policy = InferencePolicy(reasoning=True, parallel_generation=True)
    result = negotiate(policy, caps)
    # Emulated capabilities never appear as provider parameters.
    assert result.provider_policy.reasoning is False
    assert result.provider_policy.parallel_generation is False


def test_emulated_capability_produces_strategy_and_plan() -> None:
    caps = ProviderCapabilities()
    policy = InferencePolicy(reasoning=True)
    result = negotiate(policy, caps)
    decision = result.decisions[0]
    assert decision.emulation_strategy is not None
    assert decision.effective_value is None  # no fake provider parameter
    directives = result.workflow_emulation_plan.directives
    assert any(d.capability == "reasoning" for d in directives)
    assert any(d.strategy == "multi_pass_reasoning" for d in directives)


def test_non_emulatable_required_rejects() -> None:
    caps = ProviderCapabilities()
    policy = InferencePolicy(tool_calling=True)
    with pytest.raises(InferenceError):
        negotiate(policy, caps)


def test_rejected_cannot_continue() -> None:
    # A rejected requirement raises; there is no result to silently continue on.
    caps = ProviderCapabilities()
    policy = InferencePolicy(tool_calling=True)
    try:
        negotiate(policy, caps)
    except InferenceError as exc:
        assert "tool_calling" in str(exc)
    else:
        raise AssertionError("expected InferenceError for rejected requirement")


def test_xhigh_requests_effort_without_pretending_native_control() -> None:
    policy = XHIGH.inference_policy()
    assert policy.reasoning is True
    assert policy.reasoning_budget is not None and policy.reasoning_budget > 0

    # A provider without native reasoning/budget/parallel support must yield
    # EMULATE (workflow approximation), never APPLY.
    caps = ProviderCapabilities()
    result = negotiate(policy, caps)
    outcomes = {d.element: d.outcome for d in result.decisions}
    assert outcomes["reasoning"] is NegotiationOutcome.EMULATE
    assert outcomes["reasoning_budget"] is NegotiationOutcome.EMULATE
    assert outcomes["parallel_generation"] is NegotiationOutcome.EMULATE
    # No emulated capability leaks into the provider policy.
    assert result.provider_policy.reasoning is False
    assert result.provider_policy.reasoning_budget is None
    assert result.provider_policy.parallel_generation is False


def test_negotiation_result_serialization_is_stable() -> None:
    caps = ProviderCapabilities(supports_tool_calling=True)
    policy = InferencePolicy(reasoning=True, tool_calling=True, max_output_tokens=1000)
    result = negotiate(policy, caps)
    assert loads(dumps(result)) == result
    assert dumps(result) == dumps(result)
