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
