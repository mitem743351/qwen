"""Test-time compute policy and budget model (Phase 10).

Separates two dimensions that must never be conflated:

- **Qwen-native inference effort** (``reasoning_effort`` / ``thinking_budget``)
  — a *provider* control over hidden reasoning depth.
- **Research-runtime test-time computation** — the bounded *workflow* work
  (retrieval, verification, computation, trajectories, critique, synthesis).

XHIGH/EXTREME mean *more bounded useful work*, never longer prompts, higher
temperature, more permissions, or hidden-reasoning storage.

The budget model is provider-neutral, restart-safe, and globally authoritative:
nested trajectories/stages inherit the remaining global budget and can never
exceed the top-level ceiling. No ``None``/infinite defaults are permitted for
XHIGH/EXTREME.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from qwen_research.common.serialization import serializable
from qwen_research.domain.errors import ValidationError

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.domain.inference import InferencePolicy


class ResourceDimension(StrEnum):
    """Named resource dimensions tracked by a test-time budget."""

    INFERENCE_CALLS = "inference_calls"
    INFERENCE_TURNS = "inference_turns"
    TOOL_CALLS = "tool_calls"
    RETRIEVAL_ROUNDS = "retrieval_rounds"
    RETRIEVAL_CANDIDATES = "retrieval_candidates"
    VERIFICATION_ROUNDS = "verification_rounds"
    COMPUTATION_ROUNDS = "computation_rounds"
    TRAJECTORIES = "trajectories"
    CRITIQUE_ROUNDS = "critique_rounds"
    SYNTHESIS_PASSES = "synthesis_passes"
    WALL_TIME = "wall_time"
    TOKENS = "tokens"


class TrajectoryStrategy(StrEnum):
    """Distinct strategies a trajectory may adopt (they must actually differ)."""

    DIRECT = "direct"
    COUNTERARGUMENT = "counterargument"
    LITERATURE = "literature"
    DATA_DRIVEN = "data_driven"
    MECHANISTIC = "mechanistic"


class CritiqueAction(StrEnum):
    """What the workflow may do after a critique (each consumes budget)."""

    NO_ACTION = "no_action"
    RETRIEVE_MORE = "retrieve_more"
    VERIFY_MORE = "verify_more"
    COMPUTE_MORE = "compute_more"
    REWRITE = "rewrite"
    REJECT_DRAFT = "reject_draft"


class RunStatus(StrEnum):
    """High-effort run completion states."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIME_LIMIT = "time_limit"
    SYNTHESIS_REQUIRED = "synthesis_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrajectoryStatus(StrEnum):
    """Explicit trajectory lifecycle states (a trajectory that stops early must
    NOT be marked COMPLETED)."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIME_LIMIT = "time_limit"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DraftStatus(StrEnum):
    """Lifecycle of the final synthesis draft."""

    DRAFT = "draft"
    CRITIQUED = "critiqued"
    REVISION_REQUIRED = "revision_required"
    REVISED = "revised"
    FINAL_CANDIDATE = "final_candidate"
    FINAL_VERIFIED = "final_verified"
    REJECTED = "rejected"


@serializable
@dataclasses.dataclass(frozen=True)
class TestTimeComputePolicy:
    """Explicit numeric ceilings for a reasoning profile.

    Every field is a concrete bound — no ``None``/infinite defaults. The
    ``native_reasoning`` field records the *provider* reasoning control the
    profile maps to (``reasoning_effort:xhigh`` or ``thinking_budget:<n>``), and
    is translated by the Qwen adapter; it is never a workflow budget.
    """

    name: str
    max_inference_calls: int
    max_inference_turns: int
    max_tool_calls: int
    max_retrieval_rounds: int
    max_retrieval_candidates: int
    max_verification_rounds: int
    max_computation_rounds: int
    max_trajectory_count: int
    max_critique_rounds: int
    max_synthesis_passes: int
    max_wall_time_seconds: float
    max_total_tokens: int
    native_reasoning: str = ""

    def __post_init__(self) -> None:
        for field in (
            "max_inference_calls",
            "max_inference_turns",
            "max_tool_calls",
            "max_retrieval_rounds",
            "max_retrieval_candidates",
            "max_verification_rounds",
            "max_computation_rounds",
            "max_trajectory_count",
            "max_critique_rounds",
            "max_synthesis_passes",
        ):
            value = getattr(self, field)
            if value < 0:
                raise ValidationError(f"{field} must be non-negative, got {value}")
        if self.max_wall_time_seconds <= 0:
            raise ValidationError("max_wall_time_seconds must be positive")
        if self.max_total_tokens < 0:
            raise ValidationError("max_total_tokens must be non-negative")

    def budget(self) -> TestTimeComputeBudget:
        """Allocate a fresh budget from this policy."""
        return TestTimeComputeBudget(
            profile=self.name,
            allocated={
                ResourceDimension.INFERENCE_CALLS: self.max_inference_calls,
                ResourceDimension.INFERENCE_TURNS: self.max_inference_turns,
                ResourceDimension.TOOL_CALLS: self.max_tool_calls,
                ResourceDimension.RETRIEVAL_ROUNDS: self.max_retrieval_rounds,
                ResourceDimension.RETRIEVAL_CANDIDATES: self.max_retrieval_candidates,
                ResourceDimension.VERIFICATION_ROUNDS: self.max_verification_rounds,
                ResourceDimension.COMPUTATION_ROUNDS: self.max_computation_rounds,
                ResourceDimension.TRAJECTORIES: self.max_trajectory_count,
                ResourceDimension.CRITIQUE_ROUNDS: self.max_critique_rounds,
                ResourceDimension.SYNTHESIS_PASSES: self.max_synthesis_passes,
                ResourceDimension.WALL_TIME: self.max_wall_time_seconds,
                ResourceDimension.TOKENS: self.max_total_tokens,
            },
        )

    def inference_policy(self) -> InferencePolicy:
        """Express this profile's *native* reasoning intent as an InferencePolicy.

        The resulting policy carries the provider-native reasoning control
        (``reasoning_effort`` or ``thinking_budget``), which the Qwen reasoning
        translator later turns into the actual request parameter. It is **not** a
        workflow budget — the workflow budget stays in
        :class:`TestTimeComputeBudget`.
        """
        from qwen_research.domain.inference import InferencePolicy

        hint = self.native_reasoning
        if hint.startswith("reasoning_effort:"):
            return InferencePolicy(reasoning=True, reasoning_effort=hint.split(":", 1)[1])
        if hint.startswith("thinking_budget:"):
            return InferencePolicy(reasoning=True, reasoning_budget=int(hint.split(":", 1)[1]))
        return InferencePolicy(reasoning=True)


#: Explicit high-effort profile ceilings. FAST/NORMAL/DEEP keep modest bounds;
#: XHIGH/EXTREME raise *workflow* budgets materially but remain finite.
PROFILE_POLICIES: dict[str, TestTimeComputePolicy] = {
    "FAST": TestTimeComputePolicy(
        name="FAST",
        max_inference_calls=1,
        max_inference_turns=1,
        max_tool_calls=4,
        max_retrieval_rounds=1,
        max_retrieval_candidates=4,
        max_verification_rounds=0,
        max_computation_rounds=0,
        max_trajectory_count=1,
        max_critique_rounds=0,
        max_synthesis_passes=1,
        max_wall_time_seconds=60.0,
        max_total_tokens=4096,
    ),
    "NORMAL": TestTimeComputePolicy(
        name="NORMAL",
        max_inference_calls=4,
        max_inference_turns=4,
        max_tool_calls=16,
        max_retrieval_rounds=2,
        max_retrieval_candidates=16,
        max_verification_rounds=1,
        max_computation_rounds=1,
        max_trajectory_count=1,
        max_critique_rounds=1,
        max_synthesis_passes=1,
        max_wall_time_seconds=180.0,
        max_total_tokens=16384,
    ),
    "DEEP": TestTimeComputePolicy(
        name="DEEP",
        max_inference_calls=8,
        max_inference_turns=8,
        max_tool_calls=32,
        max_retrieval_rounds=3,
        max_retrieval_candidates=32,
        max_verification_rounds=2,
        max_computation_rounds=2,
        max_trajectory_count=2,
        max_critique_rounds=2,
        max_synthesis_passes=2,
        max_wall_time_seconds=300.0,
        max_total_tokens=32768,
    ),
    "XHIGH": TestTimeComputePolicy(
        name="XHIGH",
        max_inference_calls=16,
        max_inference_turns=16,
        max_tool_calls=60,
        max_retrieval_rounds=5,
        max_retrieval_candidates=64,
        max_verification_rounds=4,
        max_computation_rounds=4,
        max_trajectory_count=3,
        max_critique_rounds=3,
        max_synthesis_passes=3,
        max_wall_time_seconds=600.0,
        max_total_tokens=65536,
        native_reasoning="reasoning_effort:xhigh",
    ),
    "EXTREME": TestTimeComputePolicy(
        name="EXTREME",
        max_inference_calls=32,
        max_inference_turns=32,
        max_tool_calls=120,
        max_retrieval_rounds=8,
        max_retrieval_candidates=128,
        max_verification_rounds=6,
        max_computation_rounds=6,
        max_trajectory_count=5,
        max_critique_rounds=5,
        max_synthesis_passes=4,
        max_wall_time_seconds=1200.0,
        max_total_tokens=131072,
        native_reasoning="reasoning_effort:xhigh",
    ),
}


def get_test_time_policy(name: str) -> TestTimeComputePolicy:
    """Return the explicit policy for a reasoning profile name."""
    try:
        return PROFILE_POLICIES[name]
    except KeyError:
        raise ValidationError(
            f"unknown reasoning profile {name!r}; expected one of {sorted(PROFILE_POLICIES)}"
        ) from None


@serializable
@dataclasses.dataclass
class TestTimeComputeBudget:
    __test__ = False  # not a pytest test class
    """A live, mutable budget with per-dimension allocated/consumed/remaining.

    ``reserve``/``commit`` are explicit: an operation must reserve before it
    spends, and commit its consumption after. ``consumed`` is monotonic — it can
    never decrease, so a restart re-loading the budget cannot reset it.
    """

    profile: str
    allocated: dict[ResourceDimension, float] = dataclasses.field(default_factory=dict)
    consumed: dict[ResourceDimension, float] = dataclasses.field(default_factory=dict)
    reserved: dict[ResourceDimension, float] = dataclasses.field(default_factory=dict)

    def allocated_for(self, dimension: ResourceDimension) -> float:
        return self.allocated.get(dimension, 0.0)

    def consumed_for(self, dimension: ResourceDimension) -> float:
        return self.consumed.get(dimension, 0.0)

    def remaining(self, dimension: ResourceDimension) -> float:
        """Remaining usable budget (allocated minus consumed minus reserved)."""
        return max(
            0.0,
            self.allocated.get(dimension, 0.0)
            - self.consumed.get(dimension, 0.0)
            - self.reserved.get(dimension, 0.0),
        )

    def can_afford(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        return self.remaining(dimension) >= amount

    def reserve(self, dimension: ResourceDimension, amount: float = 1.0) -> bool:
        """Reserve *amount* of *dimension*; returns False if not affordable.

        A failed reservation never partially mutates the budget.
        """
        if amount < 0:
            raise ValidationError("reservation amount must be non-negative")
        if self.remaining(dimension) < amount:
            return False
        self.reserved[dimension] = self.reserved.get(dimension, 0.0) + amount
        return True

    def commit(self, dimension: ResourceDimension, amount: float = 1.0) -> None:
        """Commit a previously-reserved amount as consumed.

        Unreserved consumption is allowed but capped by the allocation (never
        overshoots a hard ceiling).
        """
        if amount < 0:
            raise ValidationError("commit amount must be non-negative")
        reserved = self.reserved.get(dimension, 0.0)
        self.reserved[dimension] = max(0.0, reserved - amount)
        self.consumed[dimension] = min(
            self.allocated.get(dimension, 0.0),
            self.consumed.get(dimension, 0.0) + amount,
        )

    def exhausted(self, dimension: ResourceDimension) -> bool:
        return not self.can_afford(dimension)

    def all_exhausted(self) -> bool:
        return all(self.exhausted(d) for d in self.allocated)

    def summary(self) -> dict[str, Any]:
        """A complete, string-keyed view (consumed defaults to 0 per dimension)."""
        allocated = {d.value: self.allocated.get(d, 0.0) for d in self.allocated}
        consumed = {d.value: self.consumed.get(d, 0.0) for d in self.allocated}
        remaining = {d.value: self.remaining(d) for d in self.allocated}
        return {
            "profile": self.profile,
            "allocated": allocated,
            "consumed": consumed,
            "remaining": remaining,
        }

    # -- persistence -------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "allocated": {d.value: v for d, v in self.allocated.items()},
            "consumed": {d.value: v for d, v in self.consumed.items()},
            "reserved": {d.value: v for d, v in self.reserved.items()},
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> TestTimeComputeBudget:
        return cls(
            profile=record["profile"],
            allocated={ResourceDimension(k): v for k, v in record["allocated"].items()},
            consumed={ResourceDimension(k): v for k, v in record["consumed"].items()},
            reserved={ResourceDimension(k): v for k, v in record.get("reserved", {}).items()},
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchQuerySet:
    """A deterministic set of query variants for diversified retrieval."""

    primary_query: str
    alternative_queries: tuple[str, ...] = ()
    counterargument_queries: tuple[str, ...] = ()
    terminology_variants: tuple[str, ...] = ()

    def all_queries(self) -> tuple[str, ...]:
        """Return the ordered query list (primary first, then variants)."""
        return (
            (self.primary_query,)
            + self.alternative_queries
            + self.counterargument_queries
            + self.terminology_variants
        )


def trajectory_query_set(strategy: TrajectoryStrategy, objective: str) -> ResearchQuerySet:
    """Build a strategy-distinct query set for a trajectory.

    Each :class:`TrajectoryStrategy` produces a **different** query emphasis so
    trajectories actually diverge rather than cloning the same work:

    - ``DIRECT`` — the objective verbatim.
    - ``COUNTERARGUMENT`` — "against"/"limitations" framing.
    - ``LITERATURE`` — review/survey framing + terminology variants.
    - ``DATA_DRIVEN`` — empirical/measurement framing.
    - ``MECHANISTIC`` — "mechanism"/"how" framing.
    """
    objective = objective.strip()
    if strategy is TrajectoryStrategy.COUNTERARGUMENT:
        return ResearchQuerySet(
            primary_query=f"arguments against {objective}",
            counterargument_queries=(f"limitations of {objective}",),
        )
    if strategy is TrajectoryStrategy.LITERATURE:
        return ResearchQuerySet(
            primary_query=f"literature review of {objective}",
            terminology_variants=(f"survey of {objective}",),
        )
    if strategy is TrajectoryStrategy.DATA_DRIVEN:
        return ResearchQuerySet(
            primary_query=f"empirical data on {objective}",
            alternative_queries=(f"measurements of {objective}",),
        )
    if strategy is TrajectoryStrategy.MECHANISTIC:
        return ResearchQuerySet(
            primary_query=f"mechanism underlying {objective}",
            alternative_queries=(f"how does {objective} work",),
        )
    return ResearchQuerySet(primary_query=objective)


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchTrajectory:
    """A bounded, distinct research trajectory (XHIGH/EXTREME)."""

    trajectory_id: str
    strategy: TrajectoryStrategy
    objective: str
    evidence_refs: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    computation_refs: tuple[str, ...] = ()
    status: str = "pending"

    @classmethod
    def create(cls, strategy: TrajectoryStrategy, objective: str) -> ResearchTrajectory:
        from qwen_research.common.ids import new_id

        return cls(
            trajectory_id=new_id("trajectory"),
            strategy=strategy,
            objective=objective,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class CritiqueRequest:
    """A model-backed critique request (never carries hidden reasoning)."""

    draft: str
    claims: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    verification_summaries: tuple[str, ...] = ()
    computation_summaries: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


@serializable
@dataclasses.dataclass(frozen=True)
class CritiqueIssue:
    severity: str
    description: str
    claim_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@serializable
@dataclasses.dataclass(frozen=True)
class CritiqueResult:
    """The outcome of a critique pass (issues + recommended action)."""

    issues: tuple[CritiqueIssue, ...] = ()
    recommended_action: CritiqueAction = CritiqueAction.NO_ACTION
    recommendation_reason: str = ""


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchSynthesisInput:
    """Structured, provenance-preserving input to the final synthesis."""

    claims: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    computations: tuple[str, ...] = ()
    trajectory_findings: tuple[str, ...] = ()
    critique_findings: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


@serializable
@dataclasses.dataclass
class HighEffortRunState:
    """The persisted logical state of a high-effort run (Phase 10.1).

    Persisted so a restart resumes trajectories/stages and budget consumption
    rather than recreating them. Only safe metadata is stored — no hidden
    reasoning, no credentials, no raw tool payloads.
    """

    run_id: str
    profile: str
    task_description: str
    budget: TestTimeComputeBudget
    trajectories: list[ResearchTrajectory] = dataclasses.field(default_factory=list)
    completed_stages: list[str] = dataclasses.field(default_factory=list)
    evidence_refs: list[str] = dataclasses.field(default_factory=list)
    claims: list[str] = dataclasses.field(default_factory=list)
    verification_refs: list[str] = dataclasses.field(default_factory=list)
    contradictions: list[str] = dataclasses.field(default_factory=list)
    computation_refs: list[str] = dataclasses.field(default_factory=list)
    critique_results: list[CritiqueResult] = dataclasses.field(default_factory=list)
    final_synthesis: str = ""
    status: str = "running"
    #: Absolute wall-clock deadline (epoch seconds). Persisted so a restart
    #: resumes with the *remaining* time, never a fresh window.
    deadline_at: float | None = None
    #: Final-draft lifecycle.
    draft: str = ""
    draft_status: str = DraftStatus.DRAFT.value
    final_verified: bool = False
    #: Explicit budget-overrun violations (never silently clamped).
    violations: list[str] = dataclasses.field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        """A primitives-only record (JSON-safe; enum keys stringified)."""
        from qwen_research.common.serialization import dumps

        return {
            "run_id": self.run_id,
            "profile": self.profile,
            "task_description": self.task_description,
            "budget": self.budget.to_record(),
            "trajectories": [dumps(t) for t in self.trajectories],
            "completed_stages": list(self.completed_stages),
            "evidence_refs": list(self.evidence_refs),
            "claims": list(self.claims),
            "verification_refs": list(self.verification_refs),
            "contradictions": list(self.contradictions),
            "computation_refs": list(self.computation_refs),
            "critique_results": [dumps(c) for c in self.critique_results],
            "final_synthesis": self.final_synthesis,
            "status": self.status,
            "deadline_at": self.deadline_at,
            "draft": self.draft,
            "draft_status": self.draft_status,
            "final_verified": self.final_verified,
            "violations": list(self.violations),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> HighEffortRunState:
        from qwen_research.common.serialization import loads

        return cls(
            run_id=record["run_id"],
            profile=record["profile"],
            task_description=record["task_description"],
            budget=TestTimeComputeBudget.from_record(record["budget"]),
            trajectories=[loads(t) for t in record.get("trajectories", [])],
            completed_stages=list(record.get("completed_stages", [])),
            evidence_refs=list(record.get("evidence_refs", [])),
            claims=list(record.get("claims", [])),
            verification_refs=list(record.get("verification_refs", [])),
            contradictions=list(record.get("contradictions", [])),
            computation_refs=list(record.get("computation_refs", [])),
            critique_results=[loads(c) for c in record.get("critique_results", [])],
            final_synthesis=record.get("final_synthesis", ""),
            status=record.get("status", "running"),
            deadline_at=record.get("deadline_at"),
            draft=record.get("draft", ""),
            draft_status=record.get("draft_status", DraftStatus.DRAFT.value),
            final_verified=record.get("final_verified", False),
            violations=list(record.get("violations", [])),
        )
