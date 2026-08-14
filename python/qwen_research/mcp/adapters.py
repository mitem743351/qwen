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

from qwen_research.domain.errors import ValidationError
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import ReasoningProfile, get_profile
from qwen_research.domain.research import ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task
from qwen_research.memory.models import ResearchMemory, ResearchQuestion
from qwen_research.memory.retriever import MemoryHit
from qwen_research.retrieval.models import DocumentView, SearchResult
from qwen_research.tools.base import Tool


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
