"""CLI entry point: run the MCP server over stdio.

Usage: ``python -m qwen_research.mcp``

Spawns an MCP server over stdio backed by an in-memory Research Runtime. This
is how Qwen Studio (or another local MCP client) connects. Local-only: no
network socket is opened.
"""

from __future__ import annotations

from qwen_research.mcp.server import run_stdio_server
from qwen_research.research.runtime import InMemoryResearchRuntime


def main() -> None:
    run_stdio_server(InMemoryResearchRuntime())


if __name__ == "__main__":
    main()
