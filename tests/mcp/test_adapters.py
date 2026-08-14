"""Schema adapter and MCP tool adapter conversions."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import SessionId, TaskId
from qwen_research.domain.errors import ValidationError
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import DEEP, XHIGH
from qwen_research.domain.research import Hypothesis, ResearchPlan, ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task, TaskStatus
from qwen_research.mcp.adapters import MCPToolAdapter, SchemaAdapter
from qwen_research.tools.base import ToolPermission, ToolResult


def test_mode_conversion() -> None:
    adapter = SchemaAdapter()
    assert adapter.mode("studio_native") is OperatingMode.STUDIO_NATIVE
    assert adapter.mode("gateway_inference") is OperatingMode.GATEWAY_INFERENCE
    assert adapter.mode("hybrid") is OperatingMode.HYBRID


def test_mode_conversion_rejects_unknown() -> None:
    adapter = SchemaAdapter()
    with pytest.raises(ValidationError):
        adapter.mode("bogus")


def test_profile_conversion() -> None:
    adapter = SchemaAdapter()
    assert adapter.profile("DEEP") is DEEP
    assert adapter.profile("XHIGH") is XHIGH


def test_profile_conversion_rejects_unknown() -> None:
    adapter = SchemaAdapter()
    with pytest.raises(ValidationError):
        adapter.profile("SUPER")


def test_metadata_conversion() -> None:
    adapter = SchemaAdapter()
    assert adapter.metadata(None) == {}
    assert adapter.metadata({"a": "b", "n": 1}) == {"a": "b", "n": "1"}


def test_session_result_projection() -> None:
    session = Session.create(project_id="p1", mode=OperatingMode.HYBRID)
    result = SchemaAdapter().session_result(session)
    assert result["session_id"] == session.session_id
    assert result["project_id"] == "p1"
    assert result["mode"] == "hybrid"
    assert "metadata" in result


def test_task_result_projection() -> None:
    task = Task.create("research q", SessionId("session_x"), DEEP.name)
    result = SchemaAdapter().task_result(task)
    assert result["task_id"] == task.task_id
    assert result["status"] == "created"
    assert result["reasoning_profile"] == "DEEP"
    assert result["session_id"] == "session_x"


def test_research_state_result_projection() -> None:
    state = ResearchState(
        task_id=TaskId("task_1"),
        current_stage=TaskStatus.PLANNED,
        plan=ResearchPlan(steps=("a", "b")),
        hypotheses=(Hypothesis("h1"),),
    )
    result = SchemaAdapter().research_state_result(state)
    assert result["task_id"] == "task_1"
    assert result["current_stage"] == "planned"
    assert result["plan"]["steps"] == ["a", "b"]
    assert result["hypotheses"] == ["h1"]


class _EchoTool:
    name = "echo"
    description = "echo a value"
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    permission = ToolPermission.READ

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult.success({"echo": arguments.get("value")})


def test_mcp_tool_adapter_wraps_neutral_tool() -> None:
    adapter = MCPToolAdapter(_EchoTool())
    assert adapter.name == "echo"
    assert adapter.description == "echo a value"
    assert adapter.schema["type"] == "object"
    assert adapter.permission == "read"
