"""MCP server construction, lifecycle, and guarded dispatch."""

from __future__ import annotations

import asyncio

import pytest
from mcp.shared.exceptions import MCPError

from qwen_research.domain.errors import ConfigurationError, PermissionError, PersistenceError
from qwen_research.mcp.config import MCPServerConfig
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, ToolPermissionPolicy
from qwen_research.mcp.server import MCPServerApp, guarded_call
from qwen_research.research.runtime import InMemoryResearchRuntime


def _runtime() -> InMemoryResearchRuntime:
    return InMemoryResearchRuntime()


def test_server_builds_and_lists_tools() -> None:
    app = MCPServerApp(_runtime())
    assert app.list_tools() == [
        "continue_task",
        "create_session",
        "execute_task",
        "get_research_state",
        "get_session",
        "get_task_state",
    ]


def test_diagnostics() -> None:
    app = MCPServerApp(_runtime())
    d = app.diagnostics()
    assert d["server"] == "qwen-research"
    assert d["transport"] == "stdio"
    assert d["status"] == "initialized"
    assert len(d["registered_tools"]) == 6
    assert d["runtime_status"] == "ok"


def test_shutdown_changes_status() -> None:
    app = MCPServerApp(_runtime())
    app.shutdown()
    assert app.status == "stopped"


def test_enabled_tools_config_filters() -> None:
    config = MCPServerConfig(enabled_tools=("get_session", "create_session"))
    app = MCPServerApp(_runtime(), config)
    assert app.list_tools() == ["create_session", "get_session"]


def test_unknown_enabled_tool_raises() -> None:
    config = MCPServerConfig(enabled_tools=("bogus",))
    with pytest.raises(ConfigurationError):
        MCPServerApp(_runtime(), config)


def _policy(analyze: bool = True) -> ToolPermissionPolicy:
    return ToolPermissionPolicy.from_config(
        {"read": True, "analyze": analyze, "write": False, "execute": False, "destructive": False},
        DEFAULT_TOOL_PERMISSIONS,
    )


def test_guarded_call_returns_success() -> None:
    result = guarded_call(_policy(), "get_session", lambda: {"ok": True})
    assert result == {"ok": True}


def test_guarded_call_denies_when_disabled() -> None:
    with pytest.raises(MCPError) as exc:
        guarded_call(_policy(analyze=False), "execute_task", lambda: None)
    assert "permission denied" in exc.value.message


def test_guarded_call_maps_internal_error() -> None:
    def boom() -> None:
        raise PersistenceError("no task")

    with pytest.raises(MCPError) as exc:
        guarded_call(_policy(), "get_task_state", boom)
    assert "no task" in exc.value.message


def test_guarded_call_maps_permission_domain_error() -> None:
    def deny() -> None:
        raise PermissionError("not allowed")

    with pytest.raises(MCPError) as exc:
        guarded_call(_policy(), "get_session", deny)
    assert "permission denied" in exc.value.message


def test_tool_catalog_async_inside_running_loop() -> None:
    app = MCPServerApp(_runtime())

    async def run() -> dict[str, dict]:
        return await app.tool_catalog_async()

    catalog = asyncio.run(run())
    assert sorted(catalog) == [
        "continue_task",
        "create_session",
        "execute_task",
        "get_research_state",
        "get_session",
        "get_task_state",
    ]
    assert "input_schema" in catalog["get_session"]
    assert "description" in catalog["get_session"]


def test_tool_catalog_sync_raises_clear_error_inside_loop() -> None:
    app = MCPServerApp(_runtime())

    async def run() -> None:
        with pytest.raises(RuntimeError, match="tool_catalog_async"):
            app.tool_catalog()

    asyncio.run(run())


def test_tool_catalog_sync_and_async_agree() -> None:
    app = MCPServerApp(_runtime())
    assert app.tool_catalog() == asyncio.run(app.tool_catalog_async())
