"""End-to-end MCP integration test over stdio (no Qwen/network required).

Spawns the real MCP server as a subprocess and connects with the official MCP
client — the same shape Qwen Studio uses — then exercises discovery,
invocation, structured results, error normalization, and shutdown.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    """Extract the single text content block from a tool result."""
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_roundtrip() -> None:
    async def run() -> None:
        async with (
            stdio_client(_server_params()) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # 1. Tool discovery
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            assert names == [
                "continue_task",
                "create_session",
                "execute_task",
                "get_research_state",
                "get_session",
                "get_task_state",
            ]

            # 2. create_session
            r = await session.call_tool(
                "create_session", {"project_id": "p1", "mode": "studio_native"}
            )
            session_obj = json.loads(_text(r))
            session_id = session_obj["session_id"]
            assert session_obj["project_id"] == "p1"
            assert session_obj["mode"] == "studio_native"

            # 3. get_session
            r = await session.call_tool("get_session", {"session_id": session_id})
            assert json.loads(_text(r))["session_id"] == session_id

            # 4. execute_task
            r = await session.call_tool(
                "execute_task",
                {
                    "description": "research X",
                    "session_id": session_id,
                    "reasoning_profile": "DEEP",
                },
            )
            task = json.loads(_text(r))
            task_id = task["task_id"]
            assert task["status"] == "planned"
            assert task["session_id"] == session_id

            # 5. continue_task
            r = await session.call_tool("continue_task", {"task_id": task_id})
            assert json.loads(_text(r))["status"] == "retrieving"

            # 6. get_task_state
            r = await session.call_tool("get_task_state", {"task_id": task_id})
            assert json.loads(_text(r))["status"] == "retrieving"

            # 7. get_research_state
            r = await session.call_tool("get_research_state", {"task_id": task_id})
            state = json.loads(_text(r))
            assert state["current_stage"] == "retrieving"
            assert state["plan"]["steps"] == ["plan", "retrieve", "reason", "verify", "synthesize"]

            # 8. Error normalization: unknown mode → safe INVALID_PARAMS error.
            with pytest.raises(MCPError) as exc:
                await session.call_tool("create_session", {"mode": "bogus"})
            assert exc.value.code == -32602
            assert "invalid arguments" in exc.value.message

            # 9. Session/task isolation: unknown session id → safe error.
            with pytest.raises(MCPError):
                await session.call_tool(
                    "execute_task", {"description": "x", "session_id": "session_missing"}
                )

            # 10. Unknown tool → the SDK surfaces an error result (is_error).
            result = await session.call_tool("no_such_tool", {})
            assert result.is_error is True

        # Exiting the client context closes stdio → the server shuts down.

    asyncio.run(run())
