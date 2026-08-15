"""MCP orchestration tool permissions and runtime roundtrip."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestration_helpers import build_runtime
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, MCPPermission
from qwen_research.orchestration.models import RunStatus
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_orchestration_tool_permissions() -> None:
    assert DEFAULT_TOOL_PERMISSIONS["plan_research"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["start_research"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["get_research_status"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["pause_research"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["resume_research"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["cancel_research"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["get_research_summary"] is MCPPermission.READ


def test_runtime_orchestration_roundtrip(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    task, plan = runtime.plan_research("what is the surface code threshold", project_id="p")
    assert plan.stages
    run = runtime.start_research(plan.plan_id)
    assert run.status is RunStatus.COMPLETED
    status = runtime.get_research_status(run.run_id)
    assert status.status == "completed"
    assert status.progress == 1.0
    summary = runtime.get_research_summary(run.run_id)
    assert summary["status"] == "completed"
    assert runtime.get_research_plan(plan.plan_id).plan_id == plan.plan_id
    assert runtime.get_research_events(run.run_id)


def test_runtime_orchestration_unavailable() -> None:
    runtime = InMemoryResearchRuntime()
    with pytest.raises(UnsupportedOperationError):
        runtime.plan_research("task", project_id="p")
    with pytest.raises(UnsupportedOperationError):
        runtime.start_research("plan_1")
    with pytest.raises(UnsupportedOperationError):
        runtime.get_research_status("run_1")
