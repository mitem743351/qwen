"""Provider-neutral inference value objects and capability negotiation.

These are contracts only: no provider implementation, no network access, no
Qwen-specific parameters. The negotiation layer is independent of any backend,
accounts for **every** declared capability, and never lets an unsupported
requirement silently disappear.

Model selection has a single authority: ``InferencePolicy.model_requirement``.
``InferenceRequest`` is a pure envelope and does not carry an independent model
requirement (Phase 1.1).
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import InferenceError, ValidationError


class NegotiationOutcome(StrEnum):
    """Outcome of intersecting an ``InferencePolicy`` with ``ProviderCapabilities``.

    - ``APPLY``   — the provider can directly satisfy the requested policy.
    - ``DEGRADE`` — the provider cannot fully satisfy the request, but a weaker
      valid behavior is accepted (e.g. a bounded lower output budget).
    - ``EMULATE`` — the provider cannot natively satisfy the capability, but the
      Research Runtime can approximate it via external workflow behavior.
    - ``REJECT``  — the capability is required and cannot be satisfied or
      safely approximated; negotiation fails explicitly.
    """

    APPLY = "apply"
    DEGRADE = "degrade"
    EMULATE = "emulate"
    REJECT = "reject"


@serializable
@dataclasses.dataclass(frozen=True)
class ProviderCapabilities:
    """What an inference backend can actually do — advertised, never assumed.

    Every field defaults to ``False``: a capability is *unsupported* unless the
    provider explicitly advertises it.
    """

    supports_reasoning: bool = False
    supports_reasoning_budget: bool = False
    supports_max_output_tokens: bool = False
    supports_temperature: bool = False
    supports_top_p: bool = False
    supports_preserved_thinking: bool = False
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    supports_streaming: bool = False
    supports_parallel_generation: bool = False
    supports_context_caching: bool = False


@serializable
@dataclasses.dataclass(frozen=True)
class ModelInfo:
    """Static identity information about a model."""

    provider: str
    model: str
    context_window: int | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class InferencePolicy:
    """A provider-neutral statement of *how* to call a model.

    Fields are capability-aligned intents (not provider parameters). A field
    being ``None``/``False`` means "not requested"; a non-default value is a
    request that negotiation must account for explicitly.

    ``model_requirement`` is the **single authoritative** model-selection
    intent. It is not a capability and is not negotiated here; a provider
    adapter later translates it into a provider-specific model identifier.
    """

    model_requirement: str | None = None
    reasoning: bool = False
    reasoning_budget: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    preserved_thinking: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    streaming: bool = False
    parallel_generation: bool = False
    context_caching: bool = False

    def __post_init__(self) -> None:
        for field, value in (
            ("reasoning_budget", self.reasoning_budget),
            ("max_output_tokens", self.max_output_tokens),
        ):
            if value is not None and value < 0:
                raise ValidationError(f"{field} must be non-negative, got {value}")
        if self.temperature is not None and self.temperature < 0:
            raise ValidationError("temperature must be non-negative")
        if self.top_p is not None and not 0.0 < self.top_p <= 1.0:
            raise ValidationError("top_p must be within (0.0, 1.0]")


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceRequest:
    """A request envelope from the Research Runtime to the Inference Runtime.

    Carries the task/context reference and the ``InferencePolicy``. It does
    **not** carry an independent model requirement — ``InferencePolicy`` is the
    single authority (Phase 1.1).
    """

    task_reference: TaskId
    inference_policy: InferencePolicy
    context: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    response_format: str | None = None
    continuation_state: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceResult:
    """A normalized inference response returned to the Research Runtime.

    Never contains hidden chain-of-thought.
    """

    status: str
    model: str
    content: str = ""
    structured_output: dict[str, Any] | None = None
    tool_calls: tuple[str, ...] = ()
    usage: dict[str, int] | None = None
    provider_metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "ok" and not self.errors


@serializable
@dataclasses.dataclass(frozen=True)
class NegotiationDecision:
    """The outcome for a single requested capability.

    Exposes everything a caller needs to reason about a decision:
    the requested capability, whether the provider supports it, the decision,
    the reason, and the effective value applied to the resulting policy.
    """

    element: str
    requested: bool
    supported: bool
    outcome: NegotiationOutcome
    reason: str
    effective_value: Any | None = None


def negotiate(
    policy: InferencePolicy, capabilities: ProviderCapabilities
) -> tuple[InferencePolicy, tuple[NegotiationDecision, ...]]:
    """Intersect *policy* with *capabilities*.

    Returns ``(applied_policy, decisions)`` where ``decisions`` contains an
    explicit record for **every** requested capability (``APPLY``, ``DEGRADE``,
    ``EMULATE``, or ``REJECT``). If any requested capability is ``REJECT``,
    raises :class:`InferenceError` — unsupported requirements never silently
    disappear and never silently continue.
    """
    decisions: list[NegotiationDecision] = []
    applied: dict[str, Any] = {"model_requirement": policy.model_requirement}

    def decide(
        element: str,
        requested: bool,
        supported: bool,
        *,
        apply: Any,
        degrade: Any,
        degrade_reason: str,
        emulate: Any | None = None,
        emulate_reason: str = "",
        reject_reason: str = "",
    ) -> None:
        if not requested:
            return
        if supported:
            decisions.append(
                NegotiationDecision(
                    element, True, True, NegotiationOutcome.APPLY, "supported", apply
                )
            )
            applied[element] = apply
        elif emulate is not None:
            decisions.append(
                NegotiationDecision(
                    element, True, False, NegotiationOutcome.EMULATE, emulate_reason, emulate
                )
            )
            applied[element] = emulate
        elif reject_reason:
            decisions.append(
                NegotiationDecision(
                    element, True, False, NegotiationOutcome.REJECT, reject_reason, None
                )
            )
        else:
            decisions.append(
                NegotiationDecision(
                    element, True, False, NegotiationOutcome.DEGRADE, degrade_reason, degrade
                )
            )
            applied[element] = degrade

    decide(
        "reasoning",
        policy.reasoning,
        capabilities.supports_reasoning,
        apply=True,
        degrade=False,  # unreachable: emulate takes precedence for reasoning
        degrade_reason="",
        emulate=True,
        emulate_reason="reasoning approximated via workflow (multi-pass/critique)",
    )
    decide(
        "reasoning_budget",
        policy.reasoning_budget is not None,
        capabilities.supports_reasoning_budget,
        apply=policy.reasoning_budget,
        degrade=None,
        degrade_reason="reasoning budget not controllable by provider",
    )
    decide(
        "max_output_tokens",
        policy.max_output_tokens is not None,
        capabilities.supports_max_output_tokens,
        apply=policy.max_output_tokens,
        degrade=None,
        degrade_reason="provider cannot cap output tokens",
    )
    decide(
        "temperature",
        policy.temperature is not None,
        capabilities.supports_temperature,
        apply=policy.temperature,
        degrade=None,
        degrade_reason="provider exposes no temperature control",
    )
    decide(
        "top_p",
        policy.top_p is not None,
        capabilities.supports_top_p,
        apply=policy.top_p,
        degrade=None,
        degrade_reason="provider exposes no top_p control",
    )
    decide(
        "preserved_thinking",
        policy.preserved_thinking,
        capabilities.supports_preserved_thinking,
        apply=True,
        degrade=False,
        degrade_reason="",
        reject_reason=(
            "preserved thinking requested but not supported and cannot be safely approximated"
        ),
    )
    decide(
        "tool_calling",
        policy.tool_calling,
        capabilities.supports_tool_calling,
        apply=True,
        degrade=False,
        degrade_reason="",
        reject_reason="tool calling requested but not supported by provider",
    )
    decide(
        "structured_output",
        policy.structured_output,
        capabilities.supports_structured_output,
        apply=True,
        degrade=False,
        degrade_reason="",
        emulate=True,
        emulate_reason="structured output emulated via constrained prompt + post-validation",
    )
    decide(
        "streaming",
        policy.streaming,
        capabilities.supports_streaming,
        apply=True,
        degrade=False,
        degrade_reason="streaming unsupported; one-shot generation used",
    )
    decide(
        "parallel_generation",
        policy.parallel_generation,
        capabilities.supports_parallel_generation,
        apply=True,
        degrade=False,
        degrade_reason="",
        emulate=True,
        emulate_reason="parallel research emulated via sequential trajectories in the workflow",
    )
    decide(
        "context_caching",
        policy.context_caching,
        capabilities.supports_context_caching,
        apply=True,
        degrade=False,
        degrade_reason="context caching unsupported; accepted without caching",
    )

    rejected = [d for d in decisions if d.outcome is NegotiationOutcome.REJECT]
    if rejected:
        raise InferenceError(
            "inference policy cannot be satisfied: "
            + "; ".join(f"{d.element} → {d.reason}" for d in rejected)
        )

    return InferencePolicy(**applied), tuple(decisions)
