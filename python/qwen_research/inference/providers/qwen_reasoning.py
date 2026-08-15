"""Qwen-native reasoning control translation (Phase 10).

Translates a reasoning profile's *native* reasoning intent — combined with the
selected model's documented capabilities — into the exact provider parameters
Qwen accepts, enforcing the documented exclusivity:

    ``reasoning_effort`` XOR ``thinking_budget``

The mapping is model-aware:

- Models that catalog ``reasoning_effort_levels`` (e.g. ``qwen3.8-max-preview``)
  map XHIGH/EXTREME to ``reasoning_effort=xhigh``.
- Models that only support a numeric ``thinking_budget`` (Qwen3.7 / Qwen3.6 /
  Qwen3.5 families) map XHIGH/EXTREME to a bounded, documented ``thinking_budget``.
- A model that supports neither degrades/emulates per the existing capability
  negotiation — native support is never fabricated.

``reasoning_effort`` and ``thinking_budget`` are never both emitted.
"""

from __future__ import annotations

import dataclasses

from qwen_research.domain.errors import InferenceError
from qwen_research.domain.inference import InferencePolicy
from qwen_research.domain.test_time import get_test_time_policy
from qwen_research.inference.providers.qwen_models import QwenModelSpec


@dataclasses.dataclass(frozen=True)
class QwenReasoningControl:
    """The translated native-reasoning parameters for a Qwen request."""

    enable_thinking: bool = False
    reasoning_effort: str | None = None
    thinking_budget: int | None = None

    def apply(self, payload: dict) -> dict:
        """Emit the reasoning params onto *payload* (no exclusivity violation)."""
        if self.enable_thinking:
            payload["enable_thinking"] = True
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.thinking_budget is not None:
            payload["thinking_budget"] = self.thinking_budget
        return payload


#: Native reasoning effort for XHIGH/EXTREME on ``reasoning_effort`` models.
_XHIGH_EFFORT = "xhigh"

#: Bounded thinking budgets (tokens) for XHIGH/EXTREME on ``thinking_budget``
#: models. These are documented-eligible, finite ceilings — never unbounded.
_XHIGH_THINKING_BUDGET = 16384
_EXTREME_THINKING_BUDGET = 32768


def translate_native_reasoning(
    policy: InferencePolicy,
    spec: QwenModelSpec,
    profile_name: str = "",
) -> QwenReasoningControl:
    """Translate *policy* + *spec* (+ profile) into Qwen reasoning params.

    Precedence: an explicit ``reasoning_effort`` on the policy wins; otherwise
    an explicit ``reasoning_budget`` is used; otherwise the profile's
    ``native_reasoning`` hint is consulted. Native support is gated on the model
    spec — never assumed.
    """
    # Explicit policy intents are authoritative.
    if policy.reasoning_effort:
        return _effort_control(policy.reasoning_effort, spec)
    if policy.reasoning_budget is not None:
        if spec.thinking_budget:
            return QwenReasoningControl(
                enable_thinking=spec.thinking,
                thinking_budget=policy.reasoning_budget,
            )
        # Model does not support numeric budget: reasoning-only, no budget.
        return QwenReasoningControl(enable_thinking=spec.thinking)

    # Profile-derived native hint.
    if profile_name:
        hint = get_test_time_policy(profile_name).native_reasoning
        if hint.startswith("reasoning_effort:"):
            return _effort_control(hint.split(":", 1)[1], spec)
        if hint.startswith("thinking_budget:"):
            budget = int(hint.split(":", 1)[1])
            return QwenReasoningControl(
                enable_thinking=spec.thinking,
                thinking_budget=budget if spec.thinking_budget else None,
            )

    # Plain reasoning (no explicit depth control).
    if policy.reasoning:
        return QwenReasoningControl(enable_thinking=spec.thinking)

    return QwenReasoningControl()


def _effort_control(effort: str, spec: QwenModelSpec) -> QwenReasoningControl:
    if spec.reasoning_effort_levels:
        if effort not in spec.reasoning_effort_levels:
            raise InferenceError(
                f"reasoning_effort {effort!r} not supported by model "
                f"{spec.model!r}; supported: {sorted(spec.reasoning_effort_levels)}"
            )
        return QwenReasoningControl(enable_thinking=True, reasoning_effort=effort)
    # Model has no reasoning_effort: degrade to a bounded thinking budget if
    # available, else reasoning-only (native xhigh is not fabricated).
    if spec.thinking_budget:
        return QwenReasoningControl(
            enable_thinking=spec.thinking,
            thinking_budget=(
                _XHIGH_THINKING_BUDGET if effort == "xhigh" else _XHIGH_THINKING_BUDGET
            ),
        )
    return QwenReasoningControl(enable_thinking=spec.thinking)


def native_reasoning_for_profile(
    profile_name: str, spec: QwenModelSpec
) -> QwenReasoningControl:
    """Profile-level native reasoning control for XHIGH/EXTREME.

    XHIGH → ``reasoning_effort=xhigh`` (or a bounded thinking budget on
    budget-only models); EXTREME → same native control (maximum supported) with
    the *workflow* budget (not the native control) providing the extra effort.
    """
    if profile_name in ("XHIGH", "EXTREME"):
        if spec.reasoning_effort_levels and "xhigh" in spec.reasoning_effort_levels:
            return QwenReasoningControl(enable_thinking=True, reasoning_effort="xhigh")
        if spec.thinking_budget:
            budget = (
                _EXTREME_THINKING_BUDGET
                if profile_name == "EXTREME"
                else _XHIGH_THINKING_BUDGET
            )
            return QwenReasoningControl(enable_thinking=spec.thinking, thinking_budget=budget)
        return QwenReasoningControl(enable_thinking=spec.thinking)
    return QwenReasoningControl(enable_thinking=spec.thinking)
