"""MCP permission model and enforcement."""

from __future__ import annotations

from qwen_research.mcp.permissions import (
    DEFAULT_TOOL_PERMISSIONS,
    MCPPermission,
    ToolPermissionPolicy,
)


def test_permission_classes() -> None:
    assert {p.value for p in MCPPermission} == {
        "read",
        "analyze",
        "write",
        "execute",
        "destructive",
    }


def test_default_tool_permissions_follow_architecture() -> None:
    # read → READ; create/execute/continue → ANALYZE (Phase 2 mapping).
    assert DEFAULT_TOOL_PERMISSIONS["get_session"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_task_state"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_research_state"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["create_session"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["execute_task"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["continue_task"] is MCPPermission.ANALYZE


def test_policy_allows_read_and_analyze_by_default() -> None:
    policy = ToolPermissionPolicy.from_config(
        {"read": True, "analyze": True, "write": False, "execute": False, "destructive": False},
        DEFAULT_TOOL_PERMISSIONS,
    )
    assert policy.allows("get_session")
    assert policy.allows("execute_task")


def test_policy_denies_disabled_class() -> None:
    policy = ToolPermissionPolicy.from_config(
        {"read": True, "analyze": False, "write": False, "execute": False, "destructive": False},
        DEFAULT_TOOL_PERMISSIONS,
    )
    assert policy.allows("get_session")  # READ still enabled
    assert not policy.allows("execute_task")  # ANALYZE disabled


def test_policy_tool_required() -> None:
    policy = ToolPermissionPolicy.from_config(
        {"read": True, "analyze": True, "write": False, "execute": False, "destructive": False},
        DEFAULT_TOOL_PERMISSIONS,
    )
    assert policy.tool_required("get_session") is MCPPermission.READ
    assert policy.tool_required("unknown_tool") is MCPPermission.READ  # conservative default
