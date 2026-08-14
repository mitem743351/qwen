"""Provider-neutral inference value objects and capability negotiation.

These are contracts only: no provider implementation, no network access, no
Qwen-specific parameters. The negotiation layer is independent of any backend
and never lets an unsupported capability silently disappear.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import InferenceError, ValidationError


class NegotiationOutcome(StrEnum):
    """Outcome of intersecting an ``InferencePolicy`` with ``ProviderCapabilities``."""

    APPLY = "apply"        # supported: pass the parameter through.
    DEGRADE = "degrade"    # unsupported: apply the closest supported behavior, record it.
    EMULATE = "emulate"    # unsupported: reproduce the intent with supported primitives.
    REJECT = "reject"      # required but impossible: fail explicitly.


@serializable
@dataclasses.dataclass(frozen=True)
class ProviderCapabilities:
    """What an inference backend can actually do — advertised, never assumed."""

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

    Contains only intents (sampling, budgets, structure, tool use, streaming);
    provider-specific parameters are derived later, in the Inference Runtime.
    """

    model_requirement: str | None = None
    sampling: str | None = None          # e.g. "deterministic", "balanced", "creative"
    max_output_tokens: int | None = None
    require_structured_output: bool = False
    allow_tool_calling: bool = False
    prefer_streaming: bool = False
    budget: int | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens < 0:
            raise ValidationError("max_output_tokens must be non-negative")
        if self.budget is not None and self.budget < 0:
            raise ValidationError("budget must be non-negative")


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceRequest:
    """A request from the Research Runtime to the Inference Runtime."""

    task_reference: TaskId
    model_requirement: str | None
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
    """The outcome for a single negotiated policy element."""

    element: str
    outcome: NegotiationOutcome
    detail: str


def negotiate(
    policy: InferencePolicy, capabilities: ProviderCapabilities
) -> tuple[InferencePolicy, tuple[NegotiationDecision, ...]]:
    """Intersect *policy* with *capabilities*, returning an applied policy + decisions.

    Every policy element that depends on a capability is either applied,
    degraded, emulated, or rejected. The returned ``decisions`` record each
    outcome so nothing disappears silently.
    """
    decisions: list[NegotiationDecision] = []
    applied: dict[str, Any] = {
        "model_requirement": policy.model_requirement,
        "sampling": policy.sampling,
        "max_output_tokens": policy.max_output_tokens,
        "require_structured_output": policy.require_structured_output,
        "allow_tool_calling": policy.allow_tool_calling,
        "prefer_streaming": policy.prefer_streaming,
        "budget": policy.budget,
    }

    if policy.max_output_tokens is not None and not capabilities.supports_max_output_tokens:
        decisions.append(
            NegotiationDecision(
                "max_output_tokens",
                NegotiationOutcome.DEGRADE,
                "provider cannot cap output tokens",
            )
        )
        applied["max_output_tokens"] = None

    if policy.sampling is not None and not (
        capabilities.supports_temperature or capabilities.supports_top_p
    ):
        decisions.append(
            NegotiationDecision(
                "sampling", NegotiationOutcome.DEGRADE, "provider exposes no sampling controls"
            )
        )
        applied["sampling"] = None

    if policy.require_structured_output:
        if capabilities.supports_structured_output:
            decisions.append(
                NegotiationDecision(
                    "require_structured_output", NegotiationOutcome.APPLY, "supported"
                )
            )
        else:
            # Structured output can be emulated via prompt-constrained JSON + validation.
            decisions.append(
                NegotiationDecision(
                    "require_structured_output",
                    NegotiationOutcome.EMULATE,
                    "emulated via constrained prompt + post-validation",
                )
            )

    if policy.allow_tool_calling and not capabilities.supports_tool_calling:
        # Tool calling is required semantics; emulation is not generally safe.
        decisions.append(
            NegotiationDecision(
                "allow_tool_calling",
                NegotiationOutcome.REJECT,
                "provider does not support tool calling",
            )
        )
        applied["allow_tool_calling"] = False

    if policy.prefer_streaming and not capabilities.supports_streaming:
        decisions.append(
            NegotiationDecision(
                "prefer_streaming",
                NegotiationOutcome.DEGRADE,
                "streaming unsupported; one-shot used",
            )
        )
        applied["prefer_streaming"] = False

    rejected = [d for d in decisions if d.outcome is NegotiationOutcome.REJECT]
    if rejected:
        raise InferenceError(
            "inference policy cannot be satisfied: "
            + "; ".join(f"{d.element} → {d.detail}" for d in rejected)
        )

    result = InferencePolicy(**applied)
    return result, tuple(decisions)
