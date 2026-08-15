"""Phase 10 native Qwen reasoning control translation tests."""

from __future__ import annotations

from typing import Any

import pytest

from qwen_research.domain.errors import InferenceError, ValidationError
from qwen_research.domain.inference import InferencePolicy
from qwen_research.inference.providers.qwen_models import QWEN_MODEL_TABLE
from qwen_research.inference.providers.qwen_reasoning import (
    native_reasoning_for_profile,
    translate_native_reasoning,
)


def _spec(model: str) -> Any:
    return QWEN_MODEL_TABLE[model]


def test_qwen38_xhigh_maps_to_reasoning_effort() -> None:
    spec = _spec("qwen3.8-max-preview")
    control = native_reasoning_for_profile("XHIGH", spec)
    assert control.reasoning_effort == "xhigh"
    assert control.thinking_budget is None  # exclusivity
    assert control.enable_thinking is True


def test_qwen37_xhigh_maps_to_thinking_budget() -> None:
    spec = _spec("qwen3.7-max")  # thinking_budget, no reasoning_effort_levels
    control = native_reasoning_for_profile("XHIGH", spec)
    assert control.reasoning_effort is None
    assert control.thinking_budget is not None
    assert control.thinking_budget > 0


def test_never_both_controls_emitted() -> None:
    for model in ("qwen3.8-max-preview", "qwen3.7-max"):
        spec = _spec(model)
        control = native_reasoning_for_profile("EXTREME", spec)
        assert not (
            control.reasoning_effort is not None and control.thinking_budget is not None
        ), model


def test_explicit_effort_on_effort_model() -> None:
    spec = _spec("qwen3.8-max-preview")
    policy = InferencePolicy(reasoning=True, reasoning_effort="xhigh")
    control = translate_native_reasoning(policy, spec)
    assert control.reasoning_effort == "xhigh"


def test_explicit_effort_unsupported_degrades_to_budget() -> None:
    spec = _spec("qwen3.7-max")  # no reasoning_effort_levels
    policy = InferencePolicy(reasoning=True, reasoning_effort="xhigh")
    # Degrades to a bounded thinking budget, never fabricates xhigh.
    control = translate_native_reasoning(policy, spec)
    assert control.reasoning_effort is None
    assert control.thinking_budget is not None


def test_effort_not_in_model_levels_rejected() -> None:
    spec = _spec("qwen3.8-max-preview")  # levels: low, medium, xhigh
    policy = InferencePolicy(reasoning=True, reasoning_effort="extreme")
    with pytest.raises(InferenceError):
        translate_native_reasoning(policy, spec)


def test_explicit_budget_on_budget_model() -> None:
    spec = _spec("qwen3.7-max")
    policy = InferencePolicy(reasoning=True, reasoning_budget=4096)
    control = translate_native_reasoning(policy, spec)
    assert control.thinking_budget == 4096


def test_explicit_budget_on_effort_model_ignores_budget() -> None:
    # qwen3.8-max-preview has thinking_budget=True and reasoning_effort_levels.
    # An explicit budget uses thinking_budget (no reasoning_effort).
    spec = _spec("qwen3.8-max-preview")
    policy = InferencePolicy(reasoning=True, reasoning_budget=2048)
    control = translate_native_reasoning(policy, spec)
    assert control.thinking_budget == 2048
    assert control.reasoning_effort is None


def test_policy_rejects_both_controls() -> None:
    with pytest.raises(ValidationError):
        InferencePolicy(reasoning=True, reasoning_effort="xhigh", reasoning_budget=100)


def test_apply_emits_exactly_one_control() -> None:
    spec = _spec("qwen3.8-max-preview")
    control = native_reasoning_for_profile("XHIGH", spec)
    payload: dict = {}
    control.apply(payload)
    assert "reasoning_effort" in payload
    assert "thinking_budget" not in payload
