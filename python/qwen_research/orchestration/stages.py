"""Workflow stage executors.

Each stage executor integrates exactly one subsystem (retrieval, verification,
computation, memory) through the application runtime. Executors never call the
subsystems' internals and never write raw SQL. Assessment is deterministic and
heuristic — Phase 7 has no model-assisted evidence judgement.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable

from qwen_research.claims.models import ClaimType
from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.common.ids import ClaimId, EvidenceId
from qwen_research.computation.models import ComputationOperation, ExecutionProfile
from qwen_research.orchestration.models import (
    ResearchPlan,
    ResearchTask,
    StageResult,
    StageType,
    SynthesisDraft,
    SynthesisRequest,
    WorkflowGuardrails,
    WorkflowRun,
    as_str_tuple,
)
from qwen_research.retrieval.models import RetrievalMode, SearchOptions
from qwen_research.verification.models import VerificationStatus


@runtime_checkable
class StageRuntime(Protocol):
    """The minimal runtime surface stage executors are allowed to touch."""

    def search_corpus(self, query: str, options: SearchOptions | None = None) -> Any: ...

    def create_claim(
        self, project_id: str, text: str, *, claim_type: ClaimType = ClaimType.UNKNOWN,
        source_refs: tuple[str, ...] = (),
    ) -> Any: ...

    def link_claim_evidence(
        self, project_id: str, claim_id: ClaimId, evidence_id: EvidenceId,
        relationship: ClaimEvidenceRelationship, rationale: str = "",
    ) -> Any: ...

    def verify_claim(self, project_id: str, claim_id: ClaimId) -> Any: ...

    def get_contradictions(self, project_id: str) -> Any: ...

    def save_research_memory(
        self, project_id: str, content: str, *, source_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (), claim_refs: tuple[str, ...] = (),
        computation_refs: tuple[str, ...] = (), dataset_refs: tuple[str, ...] = (),
        status: str = "proposed", provenance: dict[str, str] | None = None,
    ) -> Any: ...

    def build_research_context(self, query: str, *, project_id: str = "default") -> Any: ...

    def describe_dataset(self, reference: Any) -> Any: ...

    def run_analysis(
        self, project_id: str, dataset_refs: Any, operation: ComputationOperation,
        parameters: dict[str, object] | None = None, *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL, seed: int | None = None,
    ) -> Any: ...


@dataclasses.dataclass(frozen=True)
class StageExecutionContext:
    """Everything a stage executor may observe (no cross-subsystem writes)."""

    task: ResearchTask
    plan: ResearchPlan
    run: WorkflowRun
    project_id: str
    runtime: StageRuntime
    outputs: dict[str, object]
    guardrails: WorkflowGuardrails


class StageExecutor(Protocol):
    """A stage executor: supports a stage type and executes it."""

    def supports(self, stage_type: StageType) -> bool: ...

    def execute(self, context: StageExecutionContext) -> StageResult: ...


# -- convenience output accessors ------------------------------------------

def _get(outputs: dict[str, object], key: str, default: object) -> object:
    return outputs.get(key, default)


def _evidence_ids(outputs: dict[str, object]) -> tuple[str, ...]:
    return as_str_tuple(outputs.get("evidence"))


def _claim_ids(outputs: dict[str, object]) -> tuple[str, ...]:
    return as_str_tuple(outputs.get("claims"))


class ClassifyExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.CLASSIFY

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed(
            {"task_type": context.task.task_type.value, "complexity": context.task.complexity.value}
        )


class PlanExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.PLAN

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed({"plan_id": context.plan.plan_id})


class RetrieveExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.RETRIEVE

    def execute(self, context: StageExecutionContext) -> StageResult:
        query = context.plan.objective
        mode = (
            RetrievalMode.LEXICAL
            if context.task.reasoning_profile == "FAST"
            else RetrievalMode.HYBRID
        )
        limit = max(1, min(20, context.plan.budget.retrieval_budget * 2))
        result = context.runtime.search_corpus(
            query, SearchOptions(limit=limit, mode=mode)
        )
        evidence = tuple(c.chunk_id for c in result.chunks)
        sources = {c.document_id for c in result.chunks}
        degradation = (result.degradation_reason,) if getattr(result, "degraded", False) else ()
        if not evidence:
            return StageResult.completed(
                {"evidence": (), "evidence_sources": ()},
                metrics={"retrieval_calls": 1, "source_diversity": 0},
                warnings=("no evidence retrieved for query",),
                degradation=degradation,
            )
        return StageResult.completed(
            {"evidence": evidence, "evidence_sources": tuple(sorted(sources))},
            references=evidence,
            metrics={"retrieval_calls": 1, "source_diversity": len(sources)},
            degradation=degradation,
        )


class ClaimExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.CLAIM

    def execute(self, context: StageExecutionContext) -> StageResult:
        if _claim_ids(context.outputs):
            return StageResult.skipped("claims already created (idempotent)")
        texts = context.plan.subquestions or (context.plan.objective,)
        claim_ids: list[str] = []
        for text in texts:
            claim = context.runtime.create_claim(
                context.project_id, text, claim_type=ClaimType.FACTUAL
            )
            claim_ids.append(claim.claim_id)
        return StageResult.completed(
            {"claims": tuple(claim_ids)},
            references=tuple(claim_ids),
            metrics={"claims_created": len(claim_ids)},
        )


class AssessEvidenceExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.ASSESS_EVIDENCE

    def execute(self, context: StageExecutionContext) -> StageResult:
        claims = _claim_ids(context.outputs)
        evidence = _evidence_ids(context.outputs)
        if not claims or not evidence:
            return StageResult.skipped("no claims/evidence to assess")
        links = 0
        for claim_id in claims:
            for evidence_id in evidence:
                context.runtime.link_claim_evidence(
                    context.project_id,
                    ClaimId(claim_id),
                    EvidenceId(evidence_id),
                    ClaimEvidenceRelationship.SUPPORTS,
                    "deterministic candidate link (no model assessment in Phase 7)",
                )
                links += 1
        return StageResult.completed(
            {"assessed_links": links},
            metrics={"links_created": links},
            warnings=("evidence linked heuristically (deterministic candidate assessment)",),
        )


class VerifyExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.VERIFY

    def execute(self, context: StageExecutionContext) -> StageResult:
        claims = _claim_ids(context.outputs)
        if not claims:
            return StageResult.skipped("no claims to verify")
        reports: list[str] = []
        statuses: list[str] = []
        for claim_id in claims:
            report = context.runtime.verify_claim(context.project_id, ClaimId(claim_id))
            reports.append(report.report_id)
            statuses.append(report.status.value)
        control: dict[str, str] = {}
        if any(s == VerificationStatus.INSUFFICIENT_EVIDENCE.value for s in statuses):
            control = {"loop": "retrieve", "reason": "evidence_gap"}
        elif any(s == VerificationStatus.CONTRADICTED.value for s in statuses):
            control = {"loop": "retrieve", "reason": "contradiction"}
        return StageResult.completed(
            {"verification_reports": tuple(reports), "verification_statuses": tuple(statuses)},
            references=tuple(reports),
            metrics={"verification_calls": len(claims)},
            control=control,
        )


class ContradictionsExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.CONTRADICTIONS

    def execute(self, context: StageExecutionContext) -> StageResult:
        contradictions = context.runtime.get_contradictions(context.project_id)
        ids = tuple(c.contradiction_id for c in contradictions)
        return StageResult.completed(
            {"contradictions": ids},
            references=ids,
            metrics={"contradiction_count": len(ids)},
        )


class CorroborateExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.CORROBORATE

    def execute(self, context: StageExecutionContext) -> StageResult:
        sources = context.outputs.get("evidence_sources", ())
        diversity = len(set(sources)) if isinstance(sources, (list, tuple)) else 0
        return StageResult.completed(
            {"source_diversity": diversity},
            metrics={"source_diversity": diversity},
            warnings=() if diversity >= 2 else ("below two-source corroboration threshold",),
        )


class DescribeDatasetExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.DESCRIBE_DATASET

    def execute(self, context: StageExecutionContext) -> StageResult:
        spec = context.plan.computation
        if spec is None or not spec.dataset_refs:
            return StageResult.skipped("no dataset reference in plan")
        profile = context.runtime.describe_dataset(spec.dataset_refs[0])
        return StageResult.completed(
            {
                "dataset_profile": {
                    "dataset_id": profile.dataset_id,
                    "row_count": profile.row_count,
                    "column_count": profile.column_count,
                }
            },
            metrics={"dataset_profiled": 1, "computation_calls": 1},
        )


class ComputeExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.COMPUTE

    def execute(self, context: StageExecutionContext) -> StageResult:
        spec = context.plan.computation
        if spec is None:
            return StageResult.skipped("no computation required by plan")
        if context.outputs.get("computations"):
            return StageResult.skipped("computation already performed (idempotent)")
        result = context.runtime.run_analysis(
            context.project_id,
            spec.dataset_refs,
            ComputationOperation(spec.operation),
            spec.parameters or {},
        )
        computation_ids = (result.computation_id,)
        return StageResult.completed(
            {"computations": computation_ids},
            references=computation_ids,
            metrics={"computation_calls": 1, "computation_status": result.status.value},
        )


class MemoryExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.MEMORY

    def execute(self, context: StageExecutionContext) -> StageResult:
        if context.outputs.get("memory_ids"):
            return StageResult.skipped("memory already persisted (idempotent)")
        evidence = _evidence_ids(context.outputs)
        claims = _claim_ids(context.outputs)
        computations = as_str_tuple(context.outputs.get("computations"))
        content = f"Research findings for: {context.plan.objective}"
        memory = context.runtime.save_research_memory(
            context.project_id,
            content,
            evidence_refs=evidence,
            claim_refs=claims,
            computation_refs=computations,
            status="proposed",
            provenance={"plan_id": context.plan.plan_id, "run_id": context.run.run_id},
        )
        return StageResult.completed(
            {"memory_ids": (memory.memory_id,)},
            references=(memory.memory_id,),
            metrics={"memory_writes": 1},
        )


class SynthesizeExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.SYNTHESIZE

    def execute(self, context: StageExecutionContext) -> StageResult:
        ctx = context.runtime.build_research_context(
            context.plan.objective, project_id=context.project_id
        )
        draft = SynthesisDraft(
            summary=f"Structured synthesis for: {context.plan.objective}",
            evidence_refs=_evidence_ids(context.outputs),
            claim_refs=_claim_ids(context.outputs),
            contradiction_refs=as_str_tuple(context.outputs.get("contradictions")),
            computation_refs=as_str_tuple(context.outputs.get("computations")),
            unresolved_questions=(),
            artifacts=(),
            status=context.run.status.value,
        )
        request = SynthesisRequest(
            task_id=context.task.task_id,
            objective=context.plan.objective,
            research_summary={
                "evidence_count": len(draft.evidence_refs),
                "claim_count": len(draft.claim_refs),
                "contradiction_count": len(draft.contradiction_refs),
                "computation_count": len(draft.computation_refs),
            },
            completion_state=context.run.status.value,
            required_output="structured synthesis draft",
            context=ctx,
        )
        return StageResult.completed(
            {
                "synthesis_draft": dataclasses.asdict(draft),
                "synthesis_request_ready": True,
                "_synthesis_request": request,
            },
            metrics={"context_evidence": len(ctx.evidence), "memory_reads": 1},
        )


class FinalizeExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.FINALIZE

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed({"finalized": True})


#: Built-in stage executors (registered in dependency order).
BUILTIN_EXECUTORS: tuple[StageExecutor, ...] = (
    ClassifyExecutor(),
    PlanExecutor(),
    RetrieveExecutor(),
    ClaimExecutor(),
    AssessEvidenceExecutor(),
    VerifyExecutor(),
    ContradictionsExecutor(),
    CorroborateExecutor(),
    DescribeDatasetExecutor(),
    ComputeExecutor(),
    MemoryExecutor(),
    SynthesizeExecutor(),
    FinalizeExecutor(),
)


def executor_registry() -> dict[StageType, StageExecutor]:
    """Build the default stage-executor registry (one executor per stage type)."""
    registry: dict[StageType, StageExecutor] = {}
    for executor in BUILTIN_EXECUTORS:
        for stage_type in StageType:
            if executor.supports(stage_type):
                registry[stage_type] = executor
    return registry
