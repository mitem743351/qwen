"""MCP ↔ domain conversion boundary.

Two adapters live here:

- :class:`SchemaAdapter` — converts between MCP tool arguments/results and the
  Research Runtime's domain objects (session, task, research state).
- :class:`MCPToolAdapter` — adapts a neutral internal :class:`Tool` (from the
  internal Tool Registry) into an MCP-exposable tool descriptor, so the MCP
  layer does not redefine business tool logic (Phase 0.75 / ADR 0020).

Neither adapter contains reasoning logic, business rules, or database/Qwen
access.
"""

from __future__ import annotations

from typing import Any

from qwen_research.claims.models import Claim
from qwen_research.claims.relationships import ClaimEvidenceLink
from qwen_research.computation.models import ComputationResult, DatasetProfile, DatasetReference
from qwen_research.contradictions.models import Contradiction
from qwen_research.domain.errors import ValidationError
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import ReasoningProfile, get_profile
from qwen_research.domain.research import ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task
from qwen_research.memory.models import ResearchMemory, ResearchQuestion
from qwen_research.memory.retriever import MemoryHit
from qwen_research.orchestration.models import (
    ResearchPlan,
    ResearchStatus,
    ResearchTask,
    WorkflowRun,
)
from qwen_research.retrieval.models import DocumentView, SearchResult
from qwen_research.tools.base import Tool
from qwen_research.verification.models import EvidenceAssessment, VerificationReport


class SchemaAdapter:
    """Converts MCP tool arguments and results to/from domain objects."""

    def mode(self, value: str) -> OperatingMode:
        try:
            return OperatingMode(value)
        except ValueError:
            raise ValidationError(
                f"unknown operating mode {value!r}; "
                f"expected one of {[m.value for m in OperatingMode]}"
            ) from None

    def profile(self, name: str) -> ReasoningProfile:
        return get_profile(name)

    def metadata(self, value: dict[str, Any] | None) -> dict[str, str]:
        if value is None:
            return {}
        return {str(k): str(v) for k, v in value.items()}

    def session_result(self, session: Session) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "mode": session.mode.value,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "metadata": dict(session.metadata),
        }

    def task_result(self, task: Task) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "description": task.description,
            "session_id": task.session_id,
            "status": task.status.value,
            "reasoning_profile": task.reasoning_profile,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "parent_task_id": task.parent_task_id,
            "metadata": dict(task.metadata),
        }

    def research_state_result(self, state: ResearchState) -> dict[str, Any]:
        return {
            "task_id": state.task_id,
            "current_stage": state.current_stage.value,
            "plan": {"steps": list(state.plan.steps), "rationale": state.plan.rationale}
            if state.plan is not None
            else None,
            "hypotheses": [h.text for h in state.hypotheses],
            "claims": list(state.claims),
            "evidence_refs": list(state.evidence_refs),
            "decisions": [{"text": d.text, "rationale": d.rationale} for d in state.decisions],
            "unresolved_questions": [q.text for q in state.unresolved_questions],
            "artifact_refs": list(state.artifact_refs),
            "verification_refs": list(state.verification_refs),
            "continuation_state": state.continuation_state,
        }

    def search_result(self, result: SearchResult) -> dict[str, Any]:
        """Project a search result into a concise, model-friendly response."""
        return {
            "query": result.query,
            "mode": result.mode,
            "results": [
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "path": c.relative_path or c.path,
                    "page": c.page,
                    "section": c.section,
                    "excerpt": c.text,
                    "score": c.score,
                    "lexical_score": c.lexical_score,
                    "semantic_score": c.semantic_score,
                    "fusion_score": c.fusion_score,
                    "rank": c.rank,
                }
                for c in result.chunks
            ],
        }

    def document_view_result(self, view: DocumentView) -> dict[str, Any]:
        """Project a document view into a concise, model-friendly response."""
        return {
            "document_id": view.document_id,
            "source_id": view.source_id,
            "root_id": view.root_id,
            "path": view.relative_path,
            "media_type": view.media_type,
            "title": view.title,
            "metadata": dict(view.metadata),
            "content_hash": view.content_hash,
            "size_bytes": view.size_bytes,
            "modified_at": view.modified_at.isoformat() if view.modified_at else None,
            "sections": [
                {"page": page, "heading": heading} for page, heading in view.sections
            ],
        }


    def memory_hits_result(self, hits: list[MemoryHit]) -> dict[str, Any]:
        """Project memory hits into a concise, model-friendly response."""
        return {
            "memories": [
                {
                    "memory_type": h.memory_type.value,
                    "memory_id": h.memory_id,
                    "project_id": h.project_id,
                    "content": h.content,
                    "refs": list(h.refs),
                    "status": h.status,
                    "score": h.score,
                }
                for h in hits
            ]
        }

    def research_questions_result(self, questions: list[ResearchQuestion]) -> dict[str, Any]:
        return {
            "questions": [
                {
                    "question_id": q.question_id,
                    "project_id": q.project_id,
                    "question": q.question,
                    "priority": q.priority,
                    "status": q.status.value,
                    "related_claims": list(q.related_claims),
                    "related_sources": list(q.related_sources),
                }
                for q in questions
            ]
        }

    def research_memory_result(self, memory: ResearchMemory) -> dict[str, Any]:
        return {
            "memory_id": memory.memory_id,
            "project_id": memory.project_id,
            "content": memory.content,
            "source_refs": list(memory.source_refs),
            "evidence_refs": list(memory.evidence_refs),
            "claim_refs": list(memory.claim_refs),
            "status": memory.status,
            "provenance": dict(memory.provenance),
            "origin": memory.origin.value,
            "version": memory.version,
        }

    # -- Phase 5 evidence-integrity projections ---------------------------

    def claim_result(self, claim: Claim) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "project_id": claim.project_id,
            "text": claim.text,
            "type": claim.type.value,
            "status": claim.status.value,
            "confidence": claim.confidence,
            "source_refs": list(claim.source_refs),
            "evidence_refs": list(claim.evidence_refs),
            "supporting_refs": list(claim.supporting_refs),
            "contradicting_refs": list(claim.contradicting_refs),
            "version": claim.version,
        }

    def claim_evidence_link_result(self, link: ClaimEvidenceLink) -> dict[str, Any]:
        return {
            "link_id": link.link_id,
            "claim_id": link.claim_id,
            "evidence_id": link.evidence_id,
            "relationship": link.relationship.value,
            "rationale": link.rationale,
            "status": link.status.value,
        }

    def evidence_assessment_result(self, assessment: EvidenceAssessment) -> dict[str, Any]:
        return {
            "assessment_id": assessment.assessment_id,
            "claim_id": assessment.claim_id,
            "evidence_id": assessment.evidence_id,
            "support_type": assessment.support_type.value,
            "rationale": assessment.rationale,
            "status": assessment.status.value,
            "quality": {
                "extraction_quality": assessment.quality.extraction_quality.value,
                "relevance": assessment.quality.relevance,
                "directness": assessment.quality.directness,
            },
        }

    def verification_report_result(self, report: VerificationReport) -> dict[str, Any]:
        return {
            "report_id": report.report_id,
            "scope": report.scope.value,
            "claim_id": report.claim_id,
            "project_id": report.project_id,
            "status": report.status.value,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity.value,
                    "entity_type": i.entity_type,
                    "entity_id": i.entity_id,
                    "message": i.message,
                }
                for i in report.issues
            ],
            "evidence": list(report.evidence),
            "contradictions": list(report.contradictions),
            "source_assessments": list(report.source_assessments),
            "coverage": {
                "claims_checked": report.coverage.claims_checked,
                "claims_with_evidence": report.coverage.claims_with_evidence,
                "claims_with_independent_corroboration": (
                    report.coverage.claims_with_independent_corroboration
                ),
                "claims_with_contradictions": report.coverage.claims_with_contradictions,
                "claims_with_unresolved_issues": report.coverage.claims_with_unresolved_issues,
            },
            "generated_at": report.generated_at.isoformat(),
        }

    def contradictions_result(self, contradictions: list[Contradiction]) -> dict[str, Any]:
        return {
            "contradictions": [
                {
                    "contradiction_id": c.contradiction_id,
                    "project_id": c.project_id,
                    "claim_a": c.claim_a,
                    "claim_b": c.claim_b,
                    "type": c.type.value,
                    "severity": c.severity.value,
                    "status": c.status.value,
                    "rationale": c.rationale,
                }
                for c in contradictions
            ]
        }

    # -- Phase 6 computation projections ----------------------------------

    def dataset_reference(self, value: dict[str, Any]) -> DatasetReference:
        """Convert an MCP dataset-reference dict into a domain object."""
        if not isinstance(value, dict):
            raise ValidationError("dataset reference must be an object")
        return DatasetReference(
            root_id=_opt_str(value, "root_id"),
            relative_path=_opt_str(value, "relative_path"),
            document_id=_opt_str(value, "document_id"),
            dataset_id=_opt_str(value, "dataset_id"),
            artifact_id=_opt_str(value, "artifact_id"),
            format=_opt_str(value, "format"),
        )

    def dataset_profile_result(self, profile: DatasetProfile) -> dict[str, Any]:
        return {
            "dataset_id": profile.dataset_id,
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "columns": [
                {
                    "name": c.name,
                    "data_type": c.data_type,
                    "null_count": c.null_count,
                    "distinct_count": c.distinct_count,
                    "min": c.min_value,
                    "max": c.max_value,
                }
                for c in profile.columns
            ],
            "size_bytes": profile.size_bytes,
            "content_hash": profile.content_hash,
            "missing_value_count": profile.missing_value_count,
            "duplicate_row_count": profile.duplicate_row_count,
        }

    def computation_result_result(self, result: ComputationResult) -> dict[str, Any]:
        return {
            "computation_id": result.computation_id,
            "project_id": result.project_id,
            "status": result.status.value,
            "operation": result.operation.value,
            "result_type": result.result_type.value,
            "value": result.value,
            "rows": result.rows,
            "metrics": dict(result.metrics),
            "artifact_refs": list(result.artifact_refs),
            "provenance": dict(result.provenance),
            "runtime_metadata": dict(result.runtime_metadata),
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error,
        }

    # -- Phase 7 orchestration projections --------------------------------

    def plan_result(self, task: ResearchTask, plan: ResearchPlan) -> dict[str, Any]:
        return {
            "plan_id": plan.plan_id,
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "complexity": task.complexity.value,
            "reasoning_profile": task.reasoning_profile,
            "objective": plan.objective,
            "stages": [
                {"stage_id": s.stage_id, "type": s.type.value, "name": s.name}
                for s in plan.stages
            ],
            "requirements": {
                "needs_retrieval": plan.requirements.needs_retrieval,
                "needs_verification": plan.requirements.needs_verification,
                "needs_computation": plan.requirements.needs_computation,
                "needs_memory": plan.requirements.needs_memory,
                "needs_contradiction_analysis": plan.requirements.needs_contradiction_analysis,
            },
            "completion_criteria": {
                "min_evidence_count": plan.completion_criteria.min_evidence_count,
                "verification_completed": plan.completion_criteria.verification_completed,
            },
        }

    def run_result(self, run: WorkflowRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "task_id": run.task_id,
            "plan_id": run.plan_id,
            "status": run.status.value,
            "current_stage": run.current_stage,
            "degradation": list(run.degradation),
            "errors": list(run.errors),
            "accounting": dict(run.accounting),
        }

    def research_status_result(self, status: ResearchStatus) -> dict[str, Any]:
        return {
            "task_id": status.task_id,
            "run_id": status.run_id,
            "status": status.status,
            "current_stage": status.current_stage,
            "progress": status.progress,
            "degradation": list(status.degradation),
            "blocking_issues": list(status.blocking_issues),
        }


class MCPToolAdapter:
    """Adapts a neutral internal :class:`Tool` into an MCP-exposable descriptor.

    The descriptor carries the tool's name, description, schema, and permission
    class — but **not** its business logic, which remains the tool's own
    ``execute()``. The MCP layer invokes the tool; it does not redefine it.
    """

    def __init__(self, tool: Tool) -> None:
        self._tool = tool

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    @property
    def schema(self) -> dict[str, Any]:
        return dict(self._tool.schema)

    @property
    def permission(self) -> str:
        return self._tool.permission.value


def _opt_str(value: dict[str, Any], key: str) -> str | None:
    v = value.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationError(f"dataset reference key {key!r} must be a string")
    return v
