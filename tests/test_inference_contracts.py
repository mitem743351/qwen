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


def test_request_and_result_contract() -> None:
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        model_requirement="reasoning",
        inference_policy=InferencePolicy(),
    )
    assert request.task_reference == TaskId("task_1")
    result = InferenceResult(status="ok", model="qwen-xyz", content="answer")
    assert result.ok is True
    assert result.errors == ()


def test_negotiation_applies_supported() -> None:
    caps = ProviderCapabilities(supports_max_output_tokens=True, supports_tool_calling=True)
    policy = InferencePolicy(max_output_tokens=100, allow_tool_calling=True)
    applied, decisions = negotiate(policy, caps)
    assert applied.max_output_tokens == 100
    assert applied.allow_tool_calling is True
    assert all(d.outcome is NegotiationOutcome.APPLY for d in decisions)


def test_negotiation_degrades_unsupported() -> None:
    caps = ProviderCapabilities()  # nothing supported
    policy = InferencePolicy(max_output_tokens=100, sampling="balanced")
    applied, decisions = negotiate(policy, caps)
    assert applied.max_output_tokens is None
    assert applied.sampling is None
    assert {d.outcome for d in decisions} == {NegotiationOutcome.DEGRADE}


def test_negotiation_emulates_structured_output() -> None:
    caps = ProviderCapabilities(supports_structured_output=False)
    policy = InferencePolicy(require_structured_output=True)
    applied, decisions = negotiate(policy, caps)
    outcomes = {d.outcome for d in decisions}
    assert NegotiationOutcome.EMULATE in outcomes
    assert applied.require_structured_output is True


def test_negotiation_rejects_required_tool_calling() -> None:
    caps = ProviderCapabilities(supports_tool_calling=False)
    policy = InferencePolicy(allow_tool_calling=True)
    with pytest.raises(InferenceError):
        negotiate(policy, caps)


def test_model_info() -> None:
    info = ModelInfo(provider="qwen", model="qwen-max", context_window=128000)
    assert info.context_window == 128000
