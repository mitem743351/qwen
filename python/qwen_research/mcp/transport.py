"""MCP transport abstraction.

The MCP server is transport-agnostic: it runs over a :class:`MCPTransport`,
so future transports (Streamable HTTP, SSE) can be added without changing tool
or Research Runtime logic. Phase 2 implements **stdio** only, local-only by
default (no network socket is opened).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from qwen_research.domain.errors import ConfigurationError


@runtime_checkable
class MCPTransport(Protocol):
    """A transport over which the MCP server can run."""

    name: str

    def serve(self, server: Any) -> None:
        """Run the given SDK MCPServer over this transport (blocking)."""
        ...

    def shutdown(self) -> None:
        """Request graceful shutdown of the transport."""
        ...


class StdioTransport:
    """MCP over standard input/output — the local-first default.

    This is how Qwen Studio (or another local MCP client) connects: the server
    is spawned as a child process and communicates over stdin/stdout. No
    network binding is involved.
    """

    name = "stdio"

    def __init__(self) -> None:
        self._shutdown_requested = False

    def serve(self, server: Any) -> None:
        # The SDK's stdio server exits cleanly when the client closes stdin.
        server.run(transport="stdio")

    def shutdown(self) -> None:
        self._shutdown_requested = True


def create_transport(name: str) -> MCPTransport:
    """Return a transport implementation for *name*."""
    if name == "stdio":
        return StdioTransport()
    raise ConfigurationError(
        f"unsupported MCP transport {name!r}; only 'stdio' is implemented in Phase 2"
    )
