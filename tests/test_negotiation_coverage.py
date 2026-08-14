"""Complete capability-negotiation coverage.

For every declared capability: APPLY when supported, the correct
DEGRADE/EMULATE/REJECT when unsupported. Uses synthetic provider capability
profiles only — no provider implementations.
"""

from __future__ import annotations

import pytest

from qwen_research.domain.errors import InferenceError
from qwen_research.domain.inference import (
    InferencePolicy,
    NegotiationOutcome,
    ProviderCapabilities,
    negotiate,
)

# (capability flag field on ProviderCapabilities, policy kwargs to request it)
CAPABILITIES: dict[str, tuple[str, dict]] = {
    "reasoning": ("supports_reasoning", {"reasoning": True}),
    "reasoning_budget": ("supports_reasoning_budget", {"reasoning_budget": 200}),
    "max_output_tokens": ("supports_max_output_tokens", {"max_output_tokens": 200}),
    "temperature": ("supports_temperature", {"temperature": 0.7}),
    "top_p": ("supports_top_p", {"top_p": 0.9}),
    "preserved_thinking": ("supports_preserved_thinking", {"preserved_thinking": True}),
    "tool_calling": ("supports_tool_calling", {"tool_calling": True}),
    "structured_output": ("supports_structured_output", {"structured_output": True}),
    "streaming": ("supports_streaming", {"streaming": True}),
    "parallel_generation": ("supports_parallel_generation", {"parallel_generation": True}),
    "context_caching": ("supports_context_caching", {"context_caching": True}),
}

# Expected outcome when the capability is requested but unsupported.
UNSUPPORTED_OUTCOME: dict[str, NegotiationOutcome] = {
    "reasoning": NegotiationOutcome.EMULATE,
    "reasoning_budget": NegotiationOutcome.DEGRADE,
    "max_output_tokens": NegotiationOutcome.DEGRADE,
    "temperature": NegotiationOutcome.DEGRADE,
    "top_p": NegotiationOutcome.DEGRADE,
    "preserved_thinking": NegotiationOutcome.REJECT,
    "tool_calling": NegotiationOutcome.REJECT,
    "structured_output": NegotiationOutcome.EMULATE,
    "streaming": NegotiationOutcome.DEGRADE,
    "parallel_generation": NegotiationOutcome.EMULATE,
    "context_caching": NegotiationOutcome.DEGRADE,
}


@pytest.mark.parametrize("capability", list(CAPABILITIES))
def test_apply_when_supported(capability: str) -> None:
    flag, request = CAPABILITIES[capability]
    caps = ProviderCapabilities(**{flag: True})
    policy = InferencePolicy(**request)
    applied, decisions = negotiate(policy, caps)
    decision = next(d for d in decisions if d.element == capability)
    assert decision.outcome is NegotiationOutcome.APPLY
    assert decision.supported is True


@pytest.mark.parametrize("capability", list(CAPABILITIES))
def test_unsupported_outcome(capability: str) -> None:
    flag, request = CAPABILITIES[capability]
    caps = ProviderCapabilities(**{flag: False})
    policy = InferencePolicy(**request)
    expected = UNSUPPORTED_OUTCOME[capability]
    if expected is NegotiationOutcome.REJECT:
        with pytest.raises(InferenceError):
            negotiate(policy, caps)
    else:
        applied, decisions = negotiate(policy, caps)
        decision = next(d for d in decisions if d.element == capability)
        assert decision.outcome is expected
        assert decision.supported is False
        # A non-APPLY decision must carry a reason and never silently vanish.
        assert decision.reason


def test_untracked_capabilities_produce_no_decision() -> None:
    # A capability not requested yields no decision record.
    caps = ProviderCapabilities()
    policy = InferencePolicy()  # nothing requested
    _, decisions = negotiate(policy, caps)
    assert decisions == ()


def test_negotiation_accounts_for_every_requested_capability() -> None:
    caps = ProviderCapabilities(
        supports_reasoning=True,
        supports_reasoning_budget=True,
        supports_max_output_tokens=True,
        supports_temperature=True,
        supports_top_p=True,
        supports_preserved_thinking=True,
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_parallel_generation=True,
        supports_context_caching=True,
    )
    policy = InferencePolicy(
        reasoning=True,
        reasoning_budget=100,
        max_output_tokens=100,
        temperature=0.7,
        top_p=0.9,
        preserved_thinking=True,
        tool_calling=True,
        structured_output=True,
        streaming=True,
        parallel_generation=True,
        context_caching=True,
    )
    _, decisions = negotiate(policy, caps)
    # model_requirement is not a capability; 11 capabilities were requested.
    assert {d.element for d in decisions} == set(CAPABILITIES)
    assert all(d.outcome is NegotiationOutcome.APPLY for d in decisions)
