"""MCP memory tools: runtime integration, permissions, isolation, safe errors."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_memory
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, MCPPermission
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_memory_tool_permissions() -> None:
    assert DEFAULT_TOOL_PERMISSIONS["get_project_memory"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_research_memory"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_open_questions"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["save_research_memory"] is MCPPermission.WRITE


def test_runtime_memory_roundtrip(tmp_path: Path) -> None:
    _, service = build_memory(tmp_path)
    runtime = InMemoryResearchRuntime(memory=service)

    saved = runtime.save_research_memory(
        "projA", "threshold claim", source_refs=("src_1",), evidence_refs=("ev_1",)
    )
    assert saved.source_refs == ("src_1",)

    hits = runtime.get_research_memory("projA")
    assert len(hits) == 1
    assert hits[0].content == "threshold claim"


def test_runtime_project_isolation(tmp_path: Path) -> None:
    _, service = build_memory(tmp_path)
    runtime = InMemoryResearchRuntime(memory=service)
    runtime.save_research_memory("A", "claim A")
    runtime.save_research_memory("B", "claim B")
    assert len(runtime.get_research_memory("A")) == 1
    assert len(runtime.get_research_memory("B")) == 1


def test_runtime_open_questions(tmp_path: Path) -> None:
    from qwen_research.memory.models import QuestionStatus

    _, service = build_memory(tmp_path)
    runtime = InMemoryResearchRuntime(memory=service)
    service.save_open_question("p", "open question?")
    questions = runtime.get_open_questions("p")
    assert len(questions) == 1
    assert questions[0].status is QuestionStatus.OPEN


def test_memory_unavailable_raises(tmp_path: Path) -> None:
    import pytest

    from qwen_research.domain.errors import UnsupportedOperationError

    runtime = InMemoryResearchRuntime()  # no memory configured
    with pytest.raises(UnsupportedOperationError):
        runtime.get_project_memory("p")
    with pytest.raises(UnsupportedOperationError):
        runtime.save_research_memory("p", "content")
