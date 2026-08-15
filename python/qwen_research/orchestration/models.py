"""Orchestration domain models.

Provider-independent, transport-neutral value objects for Phase 7 research
orchestration: richer task metadata, deterministic classification, structured
research plans, workflow runs/stages/events, and the synthesis boundary. No
hidden chain-of-thought is stored anywhere — only structured planning and
execution state.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.computation.models import DatasetReference
from qwen_research.domain.reasoning import ReasoningBudget


class TaskType(StrEnum):
    """The controlled task-type vocabulary (deterministic classification only)."""

    QUESTION_ANSWERING = "question_answering"
    DEEP_RESEARCH = "deep_research"
    LITERATURE_REVIEW = "literature_review"
    FACT_CHECK = "fact_check"
    DATA_ANALYSIS = "data_analysis"
    COMPARISON = "comparison"
    TECHNICAL_ANALYSIS = "technical_analysis"
    SYNTHESIS = "synthesis"
    REPORT_GENERATION = "report_generation"
    CUSTOM = "custom"


class TaskComplexity(StrEnum):
    """Routing heuristic — never a claim about true difficulty."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class StageType(StrEnum):
    """Explicit workflow stage types (inference stages are future-only)."""

    CLASSIFY = "classify"
    PLAN = "plan"
    RETRIEVE = "retrieve"
    ASSESS_EVIDENCE = "assess_evidence"
    CLAIM = "claim"
    VERIFY = "verify"
    CONTRADICTIONS = "contradictions"
    CORROBORATE = "corroborate"
    DESCRIBE_DATASET = "describe_dataset"
    COMPUTE = "compute"
    MEMORY = "memory"
    SYNTHESIZE = "synthesize"
    FINALIZE = "finalize"
    CUSTOM = "custom"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class RunStatus(StrEnum):
    """Workflow run lifecycle.

    ``workflow-complete`` (the deterministic stages finished) is **never**
    ``answer-complete`` (the question is actually answered). A model-free
    workflow therefore ends at ``READY_FOR_SYNTHESIS`` (clean) or
    ``SYNTHESIS_REQUIRED`` (degraded), not ``COMPLETED`` — the latter is the
    reserved "answer complete" terminal for the future inference phase and is
    never produced by the deterministic engine.
    """

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    BLOCKED = "blocked"
    COMPLETED = "completed"  # answer-complete (reserved; never set in Phase 7)
    READY_FOR_SYNTHESIS = "ready_for_synthesis"
    SYNTHESIS_REQUIRED = "synthesis_required"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    CREATED = "created"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIED = "retried"
    PAUSED = "paused"
    RESUMED = "resumed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


_TERMINAL_RUN_STATUSES: frozenset[RunStatus] = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.READY_FOR_SYNTHESIS,
        RunStatus.SYNTHESIS_REQUIRED,
        RunStatus.PARTIAL,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.BLOCKED,
    }
)


def is_terminal_run_status(status: RunStatus) -> bool:
    return status in _TERMINAL_RUN_STATUSES


def as_str_tuple(value: object) -> tuple[str, ...]:
    """Coerce a list/tuple of values (e.g. persisted ids) into a str tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return ()


@serializable
@dataclasses.dataclass(frozen=True)
class RetryPolicy:
    """Explicit retry behavior for a stage (transient failures only)."""

    max_attempts: int = 1
    retryable_errors: tuple[str, ...] = ()
    backoff_seconds: float = 0.0


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchStage:
    """One explicit stage in a research plan."""

    stage_id: str
    type: StageType
    name: str
    dependencies: tuple[str, ...] = ()
    status: StageStatus = StageStatus.PENDING
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    retry_policy: RetryPolicy = dataclasses.field(default_factory=RetryPolicy)
    budget: int = 1
    attempts: int = 0


@serializable
@dataclasses.dataclass(frozen=True)
class PlanRequirements:
    """Capabilities a plan explicitly requires (never inferred ad hoc)."""

    needs_retrieval: bool = False
    needs_verification: bool = False
    needs_computation: bool = False
    needs_memory: bool = False
    needs_contradiction_analysis: bool = False
    needs_artifacts: bool = False


@serializable
@dataclasses.dataclass(frozen=True)
class CompletionCriteria:
    """Explicit completion conditions — a task is not "done" just because stages ran."""

    min_evidence_count: int = 0
    #: Minimum number of **independent sources** (Phase-5 ``SourceIndependence``),
    #: *not* distinct documents. Two chunks from one paper are one source; two
    #: same-publisher papers are one source.
    min_source_diversity: int = 1
    verification_completed: bool = False
    critical_contradictions_resolved: bool = False
    dataset_profiled: bool = False
    analysis_completed: bool = False
    result_persisted: bool = False
    provenance_recorded: bool = False


@serializable
@dataclasses.dataclass(frozen=True)
class ComputationSpec:
    """A deterministic computation request a plan may carry (COMPUTE stage)."""

    operation: str
    dataset_refs: tuple[DatasetReference, ...] = ()
    parameters: dict[str, object] = dataclasses.field(default_factory=dict)


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchPlan:
    """A structured, serializable, resumable plan (no hidden reasoning)."""

    plan_id: str
    task_id: TaskId
    objective: str
    assumptions: tuple[str, ...]
    subquestions: tuple[str, ...]
    stages: tuple[ResearchStage, ...]
    requirements: PlanRequirements
    completion_criteria: CompletionCriteria
    budget: ReasoningBudget
    computation: ComputationSpec | None = None
    missing_capabilities: tuple[str, ...] = ()
    created_at: datetime = dataclasses.field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        task_id: TaskId,
        objective: str,
        stages: tuple[ResearchStage, ...],
        *,
        assumptions: tuple[str, ...] = (),
        subquestions: tuple[str, ...] = (),
        requirements: PlanRequirements | None = None,
        completion_criteria: CompletionCriteria | None = None,
        budget: ReasoningBudget | None = None,
        computation: ComputationSpec | None = None,
        missing_capabilities: tuple[str, ...] = (),
    ) -> ResearchPlan:
        return cls(
            plan_id=new_id("plan"),
            task_id=task_id,
            objective=objective,
            assumptions=assumptions,
            subquestions=subquestions,
            stages=stages,
            requirements=requirements or PlanRequirements(),
            completion_criteria=completion_criteria or CompletionCriteria(),
            budget=budget or ReasoningBudget(1, 1, 1, 1, 1, 1),
            computation=computation,
            missing_capabilities=tuple(missing_capabilities),
            created_at=utc_now(),
        )


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowRun:
    """Resumable execution state for one plan run."""

    run_id: str
    task_id: TaskId
    plan_id: str
    workflow_id: str
    status: RunStatus
    current_stage: str | None
    stages: tuple[ResearchStage, ...]
    outputs: dict[str, object]
    counters: dict[str, int]
    accounting: dict[str, int]
    degradation: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    completion_notes: tuple[str, ...]
    created_at: datetime
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def create(
        cls, task_id: TaskId, plan: ResearchPlan, workflow_id: str
    ) -> WorkflowRun:
        now = utc_now()
        return cls(
            run_id=new_id("run"),
            task_id=task_id,
            plan_id=plan.plan_id,
            workflow_id=workflow_id,
            status=RunStatus.CREATED,
            current_stage=None,
            stages=tuple(plan.stages),
            outputs={},
            counters={"evidence_rounds": 0, "verification_rounds": 0, "computation_rounds": 0},
            accounting={},
            # Seed degradation from capabilities the plan required but which
            # were unavailable at plan time (explicit, never silent).
            degradation=tuple(plan.missing_capabilities),
            warnings=(),
            errors=(),
            completion_notes=(),
            created_at=now,
            started_at=None,
            updated_at=now,
            completed_at=None,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowEvent:
    """A structured workflow event (no hidden reasoning is ever logged)."""

    event_id: str
    run_id: str
    stage_id: str | None
    event_type: EventType
    status: str
    timestamp: datetime
    references: tuple[str, ...] = ()
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        run_id: str,
        event_type: EventType,
        status: str,
        *,
        stage_id: str | None = None,
        references: tuple[str, ...] = (),
        metadata: dict[str, str] | None = None,
    ) -> WorkflowEvent:
        return cls(
            event_id=new_id("event"),
            run_id=run_id,
            stage_id=stage_id,
            event_type=event_type,
            status=status,
            timestamp=utc_now(),
            references=references,
            metadata=dict(metadata or {}),
        )


@serializable
@dataclasses.dataclass(frozen=True)
class StageResult:
    """The outcome of executing one stage.

    ``warnings`` are informational notes; ``degradation`` records genuine
    capability degradation (a backend fell back or returned nothing usable),
    which forces a ``PARTIAL`` outcome rather than silent success.
    """

    status: StageStatus
    outputs: dict[str, object] = dataclasses.field(default_factory=dict)
    references: tuple[str, ...] = ()
    metrics: dict[str, object] = dataclasses.field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    degradation: tuple[str, ...] = ()
    control: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def completed(
        cls,
        outputs: dict[str, object] | None = None,
        *,
        references: tuple[str, ...] = (),
        metrics: dict[str, object] | None = None,
        warnings: tuple[str, ...] = (),
        degradation: tuple[str, ...] = (),
        control: dict[str, str] | None = None,
    ) -> StageResult:
        return cls(
            status=StageStatus.COMPLETED,
            outputs=dict(outputs or {}),
            references=references,
            metrics=dict(metrics or {}),
            warnings=warnings,
            degradation=degradation,
            control=dict(control or {}),
        )

    @classmethod
    def skipped(cls, reason: str) -> StageResult:
        return cls(status=StageStatus.SKIPPED, outputs={}, warnings=(reason,))


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchTask:
    """Richer orchestration-level task metadata (correlates with domain Task by id)."""

    task_id: TaskId
    session_id: str
    project_id: str
    title: str
    description: str
    task_type: TaskType
    complexity: TaskComplexity
    reasoning_profile: str
    plan_id: str | None
    workflow_id: str | None
    status: str
    parent_task_id: TaskId | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        project_id: str,
        description: str,
        task_type: TaskType,
        complexity: TaskComplexity,
        reasoning_profile: str,
        *,
        session_id: str = "default",
        title: str | None = None,
        parent_task_id: TaskId | None = None,
    ) -> ResearchTask:
        now = utc_now()
        return cls(
            task_id=TaskId(new_id("task")),
            session_id=session_id,
            project_id=project_id,
            title=title or description[:80],
            description=description,
            task_type=task_type,
            complexity=complexity,
            reasoning_profile=reasoning_profile,
            plan_id=None,
            workflow_id=None,
            status="created",
            parent_task_id=parent_task_id,
            created_at=now,
            updated_at=now,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchStatus:
    """Compact workflow status for observability/MCP."""

    task_id: TaskId
    run_id: str
    status: str
    current_stage: str | None
    progress: float
    degradation: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    blocking_issues: tuple[str, ...]
    #: Distinct documents represented (diagnostic only).
    document_count: int
    #: Independent sources per Phase-5 SourceIndependence (the authoritative
    #: diversity metric; satisfies "independent sources" requirements).
    independent_source_count: int
    started_at: datetime | None
    updated_at: datetime | None


@dataclasses.dataclass(frozen=True)
class SynthesisRequest:
    """Provider-neutral synthesis boundary (the future inference bridge)."""

    task_id: TaskId
    objective: str
    research_summary: dict[str, object]
    completion_state: str
    required_output: str
    context: object | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class SynthesisDraft:
    """A structured intermediate synthesis result (never polished prose)."""

    summary: str
    evidence_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    contradiction_refs: tuple[str, ...]
    computation_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    artifacts: tuple[str, ...]
    status: str


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchCapability:
    """A neutral capability descriptor for planner/registry use."""

    name: str
    description: str
    required_permission: str
    availability: str  # "available" | "unavailable" | "degraded"


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchTrajectory:
    """Interface-only parallel trajectory (no multi-model inference yet)."""

    trajectory_id: str
    run_id: str
    objective: str
    state: str
    result_refs: tuple[str, ...] = ()


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowGuardrails:
    """Orchestration budgets (not model-token budgets)."""

    max_stages: int = 64
    max_retries: int = 3
    max_retrieval_rounds: int = 3
    max_verification_rounds: int = 3
    max_computation_rounds: int = 3
    max_time_seconds: float = 3600.0
    max_tool_calls: int = 256
