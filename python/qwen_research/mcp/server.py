"""The MCP server — a thin external adapter over the Research Runtime.

Owns: protocol handling, tool registration, request validation, permission
checks, schema translation, error normalization, transport, and lifecycle.

Does **not** own: research planning, reasoning profiles, retrieval, memory,
verification, workflow logic, provider selection, or provider API calls. The
Research Runtime and Domain layers have no dependency on this module.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer as SDKMCPServer
from mcp.shared.exceptions import MCPError

from qwen_research.common.ids import SessionId, TaskId
from qwen_research.domain.errors import ConfigurationError, PermissionError
from qwen_research.mcp.adapters import SchemaAdapter
from qwen_research.mcp.config import MCPServerConfig
from qwen_research.mcp.errors import map_error
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, ToolPermissionPolicy
from qwen_research.mcp.schemas import (
    DEFAULT_TOOLS,
    TOOL_DESCRIPTIONS,
    DescriptionParam,
    MetadataParam,
    ModeParam,
    OptionalSessionIdParam,
    ProjectIdParam,
    ReasoningProfileParam,
    SessionIdParam,
    TaskIdParam,
)
from qwen_research.mcp.transport import MCPTransport, create_transport
from qwen_research.research.interfaces import ResearchRuntime

logger = logging.getLogger("qwen_research.mcp")

T = TypeVar("T")


def guarded_call(
    policy: ToolPermissionPolicy,
    tool_name: str,
    fn: Callable[[], T],
) -> T:
    """Enforce permissions and map internal errors to safe MCP errors.

    Raises :class:`MCPError` for permission denials and for any internal
    exception (mapped via :func:`map_error`). Never leaks tracebacks or
    secrets.
    """
    required = policy.tool_required(tool_name)
    if not policy.allows(tool_name):
        info = map_error(
            PermissionError(f"tool {tool_name!r} requires {required.value!r} permission")
        )
        raise MCPError(code=info.code, message=info.message, data={"category": info.category})
    try:
        return fn()
    except MCPError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every internal error
        info = map_error(exc)
        raise MCPError(
            code=info.code, message=info.message, data={"category": info.category}
        ) from None


class MCPServerApp:
    """The MCP server application: SDK server + tools + lifecycle."""

    def __init__(
        self,
        runtime: ResearchRuntime,
        config: MCPServerConfig | None = None,
        transport: MCPTransport | None = None,
    ) -> None:
        self._runtime = runtime
        self._config = config or MCPServerConfig()
        self._adapter = SchemaAdapter()
        self._policy = ToolPermissionPolicy.from_config(
            self._config.permissions, DEFAULT_TOOL_PERMISSIONS
        )
        self._transport = transport or create_transport(self._config.transport)
        self._status = "initialized"
        self._server = self._build_server()

    # -- lifecycle --------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    def serve(self) -> None:
        """Run the server over its transport (blocking)."""
        self._status = "serving"
        logger.info(
            "MCP server starting (name=%s transport=%s)",
            self._config.name,
            self._config.transport,
        )
        try:
            self._transport.serve(self._server)
        finally:
            self._status = "stopped"
            logger.info("MCP server stopped")

    def shutdown(self) -> None:
        """Request graceful shutdown."""
        self._transport.shutdown()
        self._status = "stopped"
        logger.info("MCP server shutdown requested")

    # -- diagnostics ------------------------------------------------------

    def tool_catalog(self) -> dict[str, dict[str, Any]]:
        """Return the authoritative MCP wire tool surface.

        Keys are tool names; values carry the tool's ``description`` and
        ``input_schema`` exactly as the SDK exposes them on the wire. This is
        the single source of truth for tests and diagnostics — there is no
        parallel hand-written schema to drift.

        (``asyncio.run`` is used because the SDK's ``list_tools`` is async;
        call this from a sync context only.)
        """
        tools = asyncio.run(self._server.list_tools())
        return {
            tool.name: {"description": tool.description, "input_schema": tool.input_schema}
            for tool in tools
        }

    def list_tools(self) -> list[str]:
        """Return the registered tool names (derived from the wire catalog)."""
        return sorted(self.tool_catalog())

    def diagnostics(self) -> dict[str, Any]:
        """Minimal local diagnostics (no sensitive data)."""
        return {
            "server": self._config.name,
            "version": self._config.version,
            "transport": self._config.transport,
            "status": self._status,
            "registered_tools": self.list_tools(),
            "runtime_status": "ok",
        }

    # -- server construction ----------------------------------------------

    def _build_server(self) -> SDKMCPServer:
        server = SDKMCPServer(name=self._config.name, version=self._config.version)
        adapter = self._adapter
        runtime = self._runtime
        policy = self._policy

        def get_session(session_id: SessionIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                session = runtime.get_session(SessionId(session_id))
                return adapter.session_result(session)

            return guarded_call(policy, "get_session", run)

        def create_session(
            project_id: ProjectIdParam = "default",
            mode: ModeParam = "studio_native",
            metadata: MetadataParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                session = runtime.create_session(
                    project_id=project_id,
                    mode=adapter.mode(mode),
                    metadata=adapter.metadata(metadata),
                )
                return adapter.session_result(session)

            return guarded_call(policy, "create_session", run)

        def execute_task(
            description: DescriptionParam,
            session_id: OptionalSessionIdParam = None,
            reasoning_profile: ReasoningProfileParam = "DEEP",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.execute_task(
                    description,
                    profile=adapter.profile(reasoning_profile),
                    session_id=SessionId(session_id) if session_id else None,
                )
                return adapter.task_result(task)

            return guarded_call(policy, "execute_task", run)

        def continue_task(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.continue_task(TaskId(task_id))
                return adapter.task_result(task)

            return guarded_call(policy, "continue_task", run)

        def get_task_state(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.inspect_task(TaskId(task_id))
                return adapter.task_result(task)

            return guarded_call(policy, "get_task_state", run)

        def get_research_state(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                state = runtime.get_state(TaskId(task_id))
                return adapter.research_state_result(state)

            return guarded_call(policy, "get_research_state", run)

        handlers: dict[str, Callable[..., Any]] = {
            "get_session": get_session,
            "create_session": create_session,
            "execute_task": execute_task,
            "continue_task": continue_task,
            "get_task_state": get_task_state,
            "get_research_state": get_research_state,
        }

        enabled = self._config.enabled_tools or DEFAULT_TOOLS
        for name in enabled:
            if name not in handlers:
                raise ConfigurationError(f"unknown MCP tool {name!r}")
            server.add_tool(handlers[name], name=name, description=TOOL_DESCRIPTIONS[name])

        return server


def run_stdio_server(runtime: ResearchRuntime, config: MCPServerConfig | None = None) -> None:
    """Convenience: build and serve the MCP server over stdio (blocking)."""
    MCPServerApp(runtime, config).serve()


__all__ = ["MCPServerApp", "guarded_call", "run_stdio_server"]
