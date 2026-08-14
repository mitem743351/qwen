"""MCP Server layer — the external capability adapter.

The MCP layer adapts the Research Runtime to the Model Context Protocol. It is
an **adapter**, not the research system: it owns protocol handling, tool
registration, request validation, permission checks, schema translation, error
normalization, and transport — and nothing else.

Dependency direction is one-way:

    MCP → Research Runtime → Domain

The Research Runtime and Domain layers must never import this package.
"""

from qwen_research.mcp.errors import MCPErrorInfo, map_error
from qwen_research.mcp.permissions import MCPPermission, ToolPermissionPolicy

__all__ = ["MCPErrorInfo", "MCPPermission", "ToolPermissionPolicy", "map_error"]
