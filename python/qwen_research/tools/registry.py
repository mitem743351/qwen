"""The internal Tool Registry.

Transport-independent: MCP, CLI, API, and workflow adapters will front this
registry (ADR 0020). Only capabilities with a reason to be exposed are
published to any given adapter.
"""

from __future__ import annotations

from qwen_research.domain.errors import ToolError
from qwen_research.tools.base import Tool


class DuplicateToolError(ToolError):
    """Raised when registering a tool whose name is already present."""


class UnknownToolError(ToolError):
    """Raised when looking up a tool that is not registered."""


class ToolRegistry:
    """A name-keyed registry of :class:`Tool` instances."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> Tool:
        try:
            return self._tools.pop(name)
        except KeyError:
            raise UnknownToolError(f"tool {name!r} is not registered") from None

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(f"tool {name!r} is not registered") from None

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def __contains__(self, name: object) -> bool:
        return name in self._tools
