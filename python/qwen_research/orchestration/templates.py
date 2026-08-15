"""Deterministic workflow templates.

Each template maps a task type to an explicit, dependency-ordered stage list
plus completion criteria and capability requirements. No model is invoked to
build a plan.
"""

from __future__ import annotations

from qwen_research.orchestration.models import (
    CompletionCriteria,
    PlanRequirements,
    ResearchStage,
    RetryPolicy,
    StageType,
    TaskType,
)

#: Transient-error retry for retrieval (a backend outage may be retried).
_RETRIEVE_RETRY = RetryPolicy(
    max_attempts=2, retryable_errors=("RetrievalBackendUnavailable",), backoff_seconds=0.05
)


def _stage(
    stage_id: str, stage_type: StageType, *, deps: tuple[str, ...] = (), name: str | None = None
) -> ResearchStage:
    return ResearchStage(
        stage_id=stage_id,
        type=stage_type,
        name=name or stage_id.replace("_", " ").title(),
        dependencies=deps,
        retry_policy=_RETRIEVE_RETRY if stage_type is StageType.RETRIEVE else RetryPolicy(),
    )


#: Templates keyed by task type. Each is a (name, stages, requirements, criteria).
def _deep_research() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("plan", StageType.PLAN, deps=("classify",)),
        _stage("retrieve", StageType.RETRIEVE, deps=("plan",)),
        _stage("assess", StageType.ASSESS_EVIDENCE, deps=("retrieve",)),
        _stage("verify", StageType.VERIFY, deps=("assess",)),
        _stage("compute", StageType.COMPUTE, deps=("verify",)),
        _stage("memory", StageType.MEMORY, deps=("verify",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("memory", "compute")),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(
        needs_retrieval=True,
        needs_verification=True,
        needs_computation=False,  # optional COMPUTE (only when a ComputationSpec is given)
        needs_memory=True,
        needs_contradiction_analysis=True,
        needs_artifacts=True,
    )
    # Note: Phase 7 has no deterministic claim source for open research, so
    # verification is *not* required here (the VERIFY stage is skipped without
    # claims); a future model-assisted planner will introduce claims.
    criteria = CompletionCriteria(
        min_evidence_count=1,
        min_source_diversity=1,
        verification_completed=False,
        critical_contradictions_resolved=False,
        provenance_recorded=True,
    )
    return stages, req, criteria


def _fact_check() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("retrieve", StageType.RETRIEVE, deps=("classify",)),
        _stage("claim", StageType.CLAIM, deps=("retrieve",)),
        _stage("assess", StageType.ASSESS_EVIDENCE, deps=("claim",)),
        _stage("verify", StageType.VERIFY, deps=("assess",)),
        _stage("contradictions", StageType.CONTRADICTIONS, deps=("verify",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("contradictions",)),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(
        needs_retrieval=True,
        needs_verification=True,
        needs_contradiction_analysis=True,
        needs_memory=False,
    )
    criteria = CompletionCriteria(
        min_evidence_count=1,
        min_source_diversity=1,
        verification_completed=True,
        critical_contradictions_resolved=True,
    )
    return stages, req, criteria


def _literature_review() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("retrieve", StageType.RETRIEVE, deps=("classify",)),
        _stage("corroborate", StageType.CORROBORATE, deps=("retrieve",)),
        _stage("contradictions", StageType.CONTRADICTIONS, deps=("corroborate",)),
        _stage("memory", StageType.MEMORY, deps=("contradictions",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("memory",)),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(
        needs_retrieval=True,
        needs_verification=False,
        needs_contradiction_analysis=True,
        needs_memory=True,
    )
    criteria = CompletionCriteria(
        min_evidence_count=2, min_source_diversity=2, provenance_recorded=True
    )
    return stages, req, criteria


def _data_analysis() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("plan", StageType.PLAN, deps=("classify",)),
        _stage("describe", StageType.DESCRIBE_DATASET, deps=("plan",)),
        _stage("compute", StageType.COMPUTE, deps=("describe",)),
        _stage("verify", StageType.VERIFY, deps=("compute",)),
        _stage("memory", StageType.MEMORY, deps=("verify",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("memory",)),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(
        needs_computation=True,
        needs_memory=True,
        needs_verification=False,
        needs_artifacts=True,
    )
    criteria = CompletionCriteria(
        min_evidence_count=0,
        min_source_diversity=0,
        dataset_profiled=True,
        analysis_completed=True,
        result_persisted=True,
        provenance_recorded=True,
    )
    return stages, req, criteria


def _technical_analysis() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("plan", StageType.PLAN, deps=("classify",)),
        _stage("retrieve", StageType.RETRIEVE, deps=("plan",)),
        _stage("assess", StageType.ASSESS_EVIDENCE, deps=("retrieve",)),
        _stage("verify", StageType.VERIFY, deps=("assess",)),
        _stage("compute", StageType.COMPUTE, deps=("verify",)),
        _stage("memory", StageType.MEMORY, deps=("verify",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("memory", "compute")),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(
        needs_retrieval=True,
        needs_verification=True,
        needs_computation=False,  # optional COMPUTE (only when a ComputationSpec is given)
        needs_memory=True,
        needs_contradiction_analysis=True,
    )
    # No deterministic claim source in Phase 7 → verification not required here.
    criteria = CompletionCriteria(
        min_evidence_count=1,
        min_source_diversity=1,
        verification_completed=False,
        provenance_recorded=True,
    )
    return stages, req, criteria


#: Default (CUSTOM) template — a minimal linear pass.
def _custom() -> tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]:
    stages = (
        _stage("classify", StageType.CLASSIFY),
        _stage("retrieve", StageType.RETRIEVE, deps=("classify",)),
        _stage("memory", StageType.MEMORY, deps=("retrieve",)),
        _stage("synthesize", StageType.SYNTHESIZE, deps=("memory",)),
        _stage("finalize", StageType.FINALIZE, deps=("synthesize",)),
    )
    req = PlanRequirements(needs_retrieval=True, needs_memory=True)
    criteria = CompletionCriteria(min_evidence_count=1, provenance_recorded=True)
    return stages, req, criteria


_Template = tuple[tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria]

_TEMPLATES: dict[TaskType, _Template] = {
    TaskType.DEEP_RESEARCH: _deep_research(),
    TaskType.FACT_CHECK: _fact_check(),
    TaskType.LITERATURE_REVIEW: _literature_review(),
    TaskType.DATA_ANALYSIS: _data_analysis(),
    TaskType.TECHNICAL_ANALYSIS: _technical_analysis(),
    TaskType.QUESTION_ANSWERING: _deep_research(),
    TaskType.COMPARISON: _technical_analysis(),
    TaskType.SYNTHESIS: _literature_review(),
    TaskType.REPORT_GENERATION: _deep_research(),
    TaskType.CUSTOM: _custom(),
}


def template_for(task_type: TaskType) -> tuple[
    tuple[ResearchStage, ...], PlanRequirements, CompletionCriteria
]:
    """Return the deterministic template for *task_type*."""
    return _TEMPLATES[task_type]
