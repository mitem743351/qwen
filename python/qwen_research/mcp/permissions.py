"""MCP permission model.

Mirrors the Phase 0.75 / Phase 1 permission architecture. Each MCP tool is
assigned a required permission class; the policy enables/disables classes
independently. ``WRITE``/``EXECUTE``/``DESTRUCTIVE`` default to disabled.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum


class MCPPermission(StrEnum):
    READ = "read"
    ANALYZE = "analyze"
    WRITE = "write"
    EXECUTE = "execute"
    DESTRUCTIVE = "destructive"


@dataclasses.dataclass(frozen=True)
class ToolPermissionPolicy:
    """The permission policy: which classes are enabled, and per-tool requirements."""

    enabled: frozenset[MCPPermission]
    tool_permissions: dict[str, MCPPermission]

    def tool_required(self, tool_name: str) -> MCPPermission:
        """Return the permission class *tool_name* requires."""
        return self.tool_permissions.get(tool_name, MCPPermission.READ)

    def allows(self, tool_name: str) -> bool:
        """Return whether *tool_name* is permitted under the current policy."""
        return self.tool_required(tool_name) in self.enabled

    @classmethod
    def from_config(
        cls,
        enabled: dict[str, bool],
        tool_permissions: dict[str, MCPPermission],
    ) -> ToolPermissionPolicy:
        return cls(
            enabled=frozenset(MCPPermission(k) for k, v in enabled.items() if v),
            tool_permissions=dict(tool_permissions),
        )


#: Default tool → permission mapping (see docs/architecture/mcp.md).
DEFAULT_TOOL_PERMISSIONS: dict[str, MCPPermission] = {
    "get_session": MCPPermission.READ,
    "get_task_state": MCPPermission.READ,
    "get_research_state": MCPPermission.READ,
    "create_session": MCPPermission.ANALYZE,
    "execute_task": MCPPermission.ANALYZE,
    "continue_task": MCPPermission.ANALYZE,
    "search_corpus": MCPPermission.READ,
    "get_source": MCPPermission.READ,
}
