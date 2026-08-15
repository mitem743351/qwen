"""Model tool set and tool profile tests (Phase 9)."""

from __future__ import annotations

from qwen_research.research.model_tools import build_model_tool_registry
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.tool_loop import (
    ANALYSIS,
    READ_ONLY,
    RESEARCH,
    ToolPermission,
)
from qwen_research.tools.registry import ToolRegistry


def _registry() -> ToolRegistry:
    runtime = InMemoryResearchRuntime()
    return build_model_tool_registry(runtime)


def test_default_model_tools_are_read_or_analyze() -> None:
    registry = _registry()
    callable_tools = {
        n for n in registry.list() if getattr(registry.get(n), "model_callable", True)
    }
    for name in callable_tools:
        assert registry.get(name).permission in (
            ToolPermission.READ,
            ToolPermission.ANALYZE,
        ), name


def test_run_python_is_never_model_callable() -> None:
    registry = _registry()
    assert registry.get("run_python").model_callable is False
    assert registry.get("run_python").permission is ToolPermission.EXECUTE


def test_write_tools_not_model_callable_by_default() -> None:
    registry = _registry()
    assert registry.get("save_research_memory").model_callable is False
    assert registry.get("save_research_memory").permission is ToolPermission.WRITE


def test_read_only_profile_excludes_analysis_tools() -> None:
    assert "run_query" not in READ_ONLY.allowed_tools
    assert "run_analysis" not in READ_ONLY.allowed_tools
    assert "search_corpus" in READ_ONLY.allowed_tools
    assert ToolPermission.ANALYZE not in READ_ONLY.allowed_permissions


def test_analysis_profile_includes_run_tools() -> None:
    assert "run_query" in ANALYSIS.allowed_tools
    assert "run_analysis" in ANALYSIS.allowed_tools
    assert ToolPermission.WRITE not in ANALYSIS.allowed_permissions


def test_research_profile_allows_write_but_not_execute() -> None:
    assert "save_research_memory" in RESEARCH.allowed_tools
    assert ToolPermission.WRITE in RESEARCH.allowed_permissions
    assert ToolPermission.EXECUTE not in RESEARCH.allowed_permissions
    assert ToolPermission.DESTRUCTIVE not in RESEARCH.allowed_permissions
    assert "run_python" not in RESEARCH.allowed_tools


def test_profiles_never_include_execute_or_destructive() -> None:
    for profile in (READ_ONLY, ANALYSIS, RESEARCH):
        assert ToolPermission.EXECUTE not in profile.allowed_permissions
        assert ToolPermission.DESTRUCTIVE not in profile.allowed_permissions
        assert "run_python" not in profile.allowed_tools
