"""Provider-neutral inference value objects and capability negotiation.

These are contracts only: no provider implementation, no network access, no
Qwen-specific parameters. The negotiation layer is independent of any backend,
accounts for **every** declared capability, and never lets an unsupported
requirement silently disappear.

Key Phase 1.2 boundary:

    Provider capability  ≠  Research Runtime capability

``EMULATE`` means *"the requested intent can be approximated by an external
workflow mechanism"* — it must **not** mean *"pretend the provider supports the
requested native parameter."* Consequently the negotiated result separates the
:class:`ProviderInferencePolicy` (what the backend will actually receive) from
the :class:`WorkflowEmulationPlan` (what the Research Runtime must do
externally). Emulated capabilities never appear as provider parameters.

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


class MessageRole(StrEnum):
    """Provider-neutral message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    """Normalized termination reasons (mapped from provider-specific values)."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    UNKNOWN = "unknown"


class StreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    USAGE = "usage"
    COMPLETED = "completed"
    ERROR = "error"


class ModelLifecycle(StrEnum):
    """Provider-neutral model release lifecycle."""

    GA = "ga"
    PREVIEW = "preview"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class ModelAvailability(StrEnum):
    """How a model is exposed (independent of its lifecycle)."""

    PUBLIC = "public"
    PLAN_RESTRICTED = "plan_restricted"
    REGION_RESTRICTED = "region_restricted"
    ENDPOINT_RESTRICTED = "endpoint_restricted"
    PRIVATE = "private"
    UNKNOWN = "unknown"


class AvailabilityPlan(StrEnum):
    """Provider-neutral availability/billing plan identifiers.

    Qwen's ``TOKEN_PLAN`` is mapped here without leaking its billing
    implementation into the domain model.
    """

    STANDARD = "standard"
    TOKEN_PLAN = "token_plan"
    ENTERPRISE = "enterprise"
    UNKNOWN = "unknown"


class ThinkingMode(StrEnum):
    """The effective thinking/reasoning mode for a model invocation.

    - ``ENABLED``  — thinking is on for this invocation (hybrid model).
    - ``DISABLED`` — thinking is off (non-thinking mode).
    - ``FORCED``   — thinking is always on for this model; it cannot be
      disabled (thinking-only models).
    """

    ENABLED = "enabled"
    DISABLED = "disabled"
    FORCED = "forced"


@serializable
@dataclasses.dataclass(frozen=True)
class ToolCall:
    """A model-generated tool request (represented, never executed here).

    ``arguments_error`` is set when the provider returned malformed /
    non-parsable tool arguments; it must be treated as a rejection signal
    (never silently normalized to ``{}``) so the controlled loop can return
    ``INVALID_ARGUMENTS`` instead of executing a broken call.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any] = dataclasses.field(default_factory=dict)
    arguments_error: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """A complete tool definition the model is allowed to call.

    Carries the full contract — name, human description, and an argument JSON
    Schema — so a provider can pass the *entire* tool schema to the model.
    Execution of any resulting :class:`ToolCall` remains a later phase; here we
    only represent the definition, never run it.

    ``parameters`` is a JSON Schema object describing the tool's arguments. It
    defaults to the empty object (no arguments).
    """

    name: str
    description: str = ""
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValidationError("tool name must not be empty")


@serializable
@dataclasses.dataclass(frozen=True)
class Message:
    """A provider-neutral chat message.

    ``reasoning_content`` is **transient**: it holds the hidden reasoning a
    provider returned on a prior assistant turn, carried forward *only* for
    multi-turn continuation (e.g. Qwen ``preserve_thinking``). It is marked
    ``transient`` so the serializer never persists it — hidden chain-of-thought
    is never written to disk or returned to the Research Runtime.
    """

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    reasoning_content: str = dataclasses.field(
        default="", repr=False, metadata={"transient": True}
    )


@serializable
@dataclasses.dataclass(frozen=True)
class ToolResult:
    """The result of executing a tool call (returned by the Research Runtime)."""

    call_id: str
    content: str
    structured_data: dict[str, Any] | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class StructuredOutputSpec:
    """A provider-neutral structured-output request."""

    schema: dict[str, Any]
    name: str | None = None
    strict: bool = False


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceStreamEvent:
    """A normalized streaming event (no provider-specific SSE structure)."""

    type: StreamEventType
    text_delta: str = ""
    tool_call_delta: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    finish_reason: str = ""
    error: str | None = None


class NegotiationOutcome(StrEnum):
    """Outcome of intersecting an ``InferencePolicy`` with ``ProviderCapabilities``.

    - ``APPLY``   — the provider can directly satisfy the requested policy.
    - ``DEGRADE`` — a weaker but semantically valid provider behavior satisfies
      the request (e.g. a bounded lower output budget, or accepting the
      provider default for an optional refinement).
    - ``EMULATE`` — the provider lacks the capability, but the Research Runtime
      can approximate the intent via an external workflow mechanism.
    - ``REJECT``  — the capability is required and cannot be satisfied or
      safely approximated; negotiation fails explicitly.
    """

    APPLY = "apply"
    DEGRADE = "degrade"
    EMULATE = "emulate"
    REJECT = "reject"


class CapabilityClass(StrEnum):
    """Provider-neutral classification of a negotiated capability.

    - ``NATIVE`` — the provider directly supports it.
    - ``WORKFLOW_EMULATABLE`` — the provider does not support it, but the
      Research Runtime can approximate the intent externally.
    - ``NON_EMULATABLE`` — the provider does not support it and the system
      cannot safely approximate it. If the request is required this is a
      ``REJECT``; if optional it degrades to the provider default.
    """

    NATIVE = "native"
    WORKFLOW_EMULATABLE = "workflow_emulatable"
    NON_EMULATABLE = "non_emulatable"


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
class ProviderLimits:
    """Quantitative limits a provider imposes on otherwise-supported capabilities.

    Used for ``DEGRADE`` when a requested numeric value exceeds the provider's
    bound (e.g. requested ``max_output_tokens=100000`` with a provider maximum
    of ``32000``). ``None`` means "no known bound".
    """

    max_output_tokens: int | None = None
    max_reasoning_budget: int | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class ModelInfo:
    """Static identity and availability information about a model."""

    provider: str
    model: str
    context_window: int | None = None
    lifecycle: ModelLifecycle = ModelLifecycle.UNKNOWN
    availability: ModelAvailability = ModelAvailability.UNKNOWN
    plans: tuple[AvailabilityPlan, ...] = ()
    regions: tuple[str, ...] = ()


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
    reasoning_effort: str = ""
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
        # reasoning_effort and reasoning_budget are mutually exclusive intents:
        # a policy must not request both native controls at once.
        if self.reasoning_effort and self.reasoning_budget is not None:
            raise ValidationError(
                "reasoning_effort and reasoning_budget are mutually exclusive"
            )


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
    tools: tuple[ToolSpec, ...] = ()
    response_format: str | None = None
    continuation_state: str | None = None
    #: Prepared provider-neutral messages (system/user/assistant/tool). When
    #: empty, the provider builds a single user message from ``context``.
    messages: tuple[Message, ...] = ()


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceResult:
    """A normalized inference response returned to the Research Runtime.

    Never contains hidden chain-of-thought. ``finish_reason`` is a normalized
    value (``stop`` / ``length`` / ``tool_calls`` / ``content_filter`` /
    ``error`` / ``unknown``); ``provider`` is the adapter id. Both are
    informational and default to empty/None for backward compatibility.

    ``reasoning_content`` is **transient**: it carries the provider's hidden
    reasoning for multi-turn continuation (e.g. Qwen ``preserve_thinking``),
    marked ``transient`` so the serializer never persists it.
    """

    status: str
    model: str
    content: str = ""
    structured_output: dict[str, Any] | None = None
    tool_calls: tuple[str, ...] = ()
    #: Rich tool-call representation (legacy ``tool_calls`` holds names/ids).
    tool_calls_structured: tuple[ToolCall, ...] = ()
    usage: dict[str, int] | None = None
    provider_metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    finish_reason: str = ""
    provider: str = ""
    reasoning_content: str = dataclasses.field(
        default="", repr=False, metadata={"transient": True}
    )

    @property
    def ok(self) -> bool:
        return self.status == "ok" and not self.errors


@serializable
@dataclasses.dataclass(frozen=True)
class NegotiationDecision:
    """The outcome for a single requested capability.

    Exposes everything a caller needs to reason about a decision: the requested
    capability, whether the provider supports it, its capability class, the
    decision, the reason, the effective provider value (if any), and the
    workflow emulation strategy (if emulated).

    - ``APPLY``  → ``capability_class = NATIVE``, ``effective_value`` = value.
    - ``DEGRADE`` → a weaker value (``effective_value`` = bound or ``None``).
    - ``EMULATE`` → ``capability_class = WORKFLOW_EMULATABLE``,
      ``emulation_strategy`` set, ``effective_value = None`` (no fake provider
      parameter).
    - ``REJECT``  → ``capability_class = NON_EMULATABLE``.
    """

    element: str
    requested: bool
    supported: bool
    capability_class: CapabilityClass
    outcome: NegotiationOutcome
    reason: str
    effective_value: Any | None = None
    emulation_strategy: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class EmulationDirective:
    """A single workflow emulation the Research Runtime must execute externally."""

    capability: str
    strategy: str


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowEmulationPlan:
    """The set of external workflow approximations for emulated capabilities.

    These are **not** provider parameters — they describe what the Research
    Runtime must do outside the model call (multi-pass reasoning, sequential
    trajectories, structured-output post-processing, etc.).
    """

    directives: tuple[EmulationDirective, ...] = ()

    def is_empty(self) -> bool:
        return not self.directives


@serializable
@dataclasses.dataclass(frozen=True)
class NegotiationResult:
    """The outcome of capability negotiation.

    ``provider_policy`` contains only what the backend will actually receive
    (native and degraded values). ``workflow_emulation_plan`` contains the
    external work for emulated capabilities. ``decisions`` records every
    requested capability explicitly.
    """

    provider_policy: InferencePolicy
    workflow_emulation_plan: WorkflowEmulationPlan
    decisions: tuple[NegotiationDecision, ...]


def negotiate(
    policy: InferencePolicy,
    capabilities: ProviderCapabilities,
    limits: ProviderLimits | None = None,
) -> NegotiationResult:
    """Intersect *policy* with *capabilities* (and optional *limits*).

    Returns a :class:`NegotiationResult` whose ``decisions`` records every
    requested capability as ``APPLY``, ``DEGRADE``, ``EMULATE``, or ``REJECT``:

    - Native + supported → ``APPLY`` (``capability_class=NATIVE``).
    - Native + over the provider limit → ``DEGRADE`` to the bound.
    - Optional + unsupported → ``DEGRADE`` to the provider default.
    - Workflow-emulatable + unsupported → ``EMULATE`` (never a provider
      parameter; recorded in the emulation plan).
    - Required + non-emulatable → ``REJECT``, raising :class:`InferenceError`.

    Unsupported requirements never silently disappear and never silently
    continue.
    """
    limits = limits or ProviderLimits()
    decisions: list[NegotiationDecision] = []
    emulations: list[EmulationDirective] = []
    # provider_policy defaults: only native/degraded values are written back.
    provider_values: dict[str, Any] = {"model_requirement": policy.model_requirement}

    def apply_native(element: str, value: Any) -> None:
        decisions.append(
            NegotiationDecision(
                element=element,
                requested=True,
                supported=True,
                capability_class=CapabilityClass.NATIVE,
                outcome=NegotiationOutcome.APPLY,
                reason="supported",
                effective_value=value,
            )
        )
        provider_values[element] = value

    def degrade_to_bound(
        element: str, value: Any, bound: int, reason: str
    ) -> None:
        decisions.append(
            NegotiationDecision(
                element=element,
                requested=True,
                supported=True,
                capability_class=CapabilityClass.NATIVE,
                outcome=NegotiationOutcome.DEGRADE,
                reason=reason,
                effective_value=bound,
            )
        )
        provider_values[element] = bound

    def degrade_to_default(element: str, value: Any, reason: str) -> None:
        decisions.append(
            NegotiationDecision(
                element=element,
                requested=True,
                supported=False,
                capability_class=CapabilityClass.NON_EMULATABLE,
                outcome=NegotiationOutcome.DEGRADE,
                reason=reason,
                effective_value=value,
            )
        )
        provider_values[element] = value

    def emulate(element: str, strategy: str, reason: str) -> None:
        decisions.append(
            NegotiationDecision(
                element=element,
                requested=True,
                supported=False,
                capability_class=CapabilityClass.WORKFLOW_EMULATABLE,
                outcome=NegotiationOutcome.EMULATE,
                reason=reason,
                effective_value=None,
                emulation_strategy=strategy,
            )
        )
        emulations.append(EmulationDirective(capability=element, strategy=strategy))
        # Do NOT write an emulated capability into provider_values.

    def reject(element: str, reason: str) -> None:
        decisions.append(
            NegotiationDecision(
                element=element,
                requested=True,
                supported=False,
                capability_class=CapabilityClass.NON_EMULATABLE,
                outcome=NegotiationOutcome.REJECT,
                reason=reason,
                effective_value=None,
            )
        )

    # reasoning
    if policy.reasoning:
        if capabilities.supports_reasoning:
            apply_native("reasoning", True)
        else:
            emulate(
                "reasoning",
                "multi_pass_reasoning",
                "no native reasoning; approximated via multi-pass workflow",
            )

    # reasoning_budget
    if policy.reasoning_budget is not None:
        if capabilities.supports_reasoning_budget:
            bound = limits.max_reasoning_budget
            if bound is not None and policy.reasoning_budget > bound:
                degrade_to_bound(
                    "reasoning_budget",
                    policy.reasoning_budget,
                    bound,
                    f"requested {policy.reasoning_budget} exceeds provider maximum {bound}",
                )
            else:
                apply_native("reasoning_budget", policy.reasoning_budget)
        else:
            emulate(
                "reasoning_budget",
                "workflow_reasoning_budget",
                "reasoning budget not provider-controllable; approximated via workflow passes",
            )

    # max_output_tokens
    if policy.max_output_tokens is not None:
        if capabilities.supports_max_output_tokens:
            bound = limits.max_output_tokens
            if bound is not None and policy.max_output_tokens > bound:
                degrade_to_bound(
                    "max_output_tokens",
                    policy.max_output_tokens,
                    bound,
                    f"requested {policy.max_output_tokens} exceeds provider maximum {bound}",
                )
            else:
                apply_native("max_output_tokens", policy.max_output_tokens)
        else:
            degrade_to_default(
                "max_output_tokens",
                None,
                "provider cannot cap output tokens; accepted without a cap",
            )

    # temperature
    if policy.temperature is not None:
        if capabilities.supports_temperature:
            apply_native("temperature", policy.temperature)
        else:
            degrade_to_default(
                "temperature", None, "provider exposes no temperature control; using default"
            )

    # top_p
    if policy.top_p is not None:
        if capabilities.supports_top_p:
            apply_native("top_p", policy.top_p)
        else:
            degrade_to_default(
                "top_p", None, "provider exposes no top_p control; using default"
            )

    # preserved_thinking (required, non-emulatable)
    if policy.preserved_thinking:
        if capabilities.supports_preserved_thinking:
            apply_native("preserved_thinking", True)
        else:
            reject(
                "preserved_thinking",
                "preserved thinking requested but not supported and cannot be safely approximated",
            )

    # tool_calling (required, non-emulatable)
    if policy.tool_calling:
        if capabilities.supports_tool_calling:
            apply_native("tool_calling", True)
        else:
            reject("tool_calling", "tool calling requested but not supported by provider")

    # structured_output (workflow-emulatable)
    if policy.structured_output:
        if capabilities.supports_structured_output:
            apply_native("structured_output", True)
        else:
            emulate(
                "structured_output",
                "postprocess_structured_output",
                "structured output emulated via constrained prompt + post-validation",
            )

    # streaming (optional)
    if policy.streaming:
        if capabilities.supports_streaming:
            apply_native("streaming", True)
        else:
            degrade_to_default(
                "streaming", False, "streaming unsupported; one-shot generation used"
            )

    # parallel_generation (workflow-emulatable)
    if policy.parallel_generation:
        if capabilities.supports_parallel_generation:
            apply_native("parallel_generation", True)
        else:
            emulate(
                "parallel_generation",
                "sequential_trajectories",
                "parallel research emulated via sequential trajectories in the workflow",
            )

    # context_caching (optional)
    if policy.context_caching:
        if capabilities.supports_context_caching:
            apply_native("context_caching", True)
        else:
            degrade_to_default(
                "context_caching", False, "context caching unsupported; accepted without caching"
            )

    rejected = [d for d in decisions if d.outcome is NegotiationOutcome.REJECT]
    if rejected:
        raise InferenceError(
            "inference policy cannot be satisfied: "
            + "; ".join(f"{d.element} → {d.reason}" for d in rejected)
        )

    return NegotiationResult(
        provider_policy=InferencePolicy(**provider_values),
        workflow_emulation_plan=WorkflowEmulationPlan(tuple(emulations)),
        decisions=tuple(decisions),
    )
