"""Neutral internal tool abstraction and registry.

MCP is one adapter over this registry, not the registry itself (ADR 0020).
"""

from qwen_research.tools.base import Tool, ToolPermission, ToolResult
from qwen_research.tools.registry import DuplicateToolError, ToolRegistry, UnknownToolError

__all__ = [
    "DuplicateToolError",
    "Tool",
    "ToolPermission",
    "ToolRegistry",
    "ToolResult",
    "UnknownToolError",
]
