"""MCP server configuration.

Minimal, secure-by-default configuration model. No large configuration
framework; loading from files/environment is a later concern.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for the MCP server adapter."""

    name: str = "qwen-research"
    version: str = "0.1.0"
    transport: str = "stdio"  # only stdio is implemented in Phase 2
    host: str = "127.0.0.1"   # local-only by default (unused by stdio)
    port: int | None = None   # unused by stdio
    #: Tools enabled for exposure. Empty means "expose the default minimal set".
    enabled_tools: tuple[str, ...] = ()
    #: Permission policy keyed by permission class → enabled.
    permissions: dict[str, bool] = dataclasses.field(
        default_factory=lambda: {
            "read": True,
            "analyze": True,
            "write": False,
            "execute": False,
            "destructive": False,
        }
    )
