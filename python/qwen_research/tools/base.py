"""The neutral internal ``Tool`` abstraction."""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from qwen_research.domain.errors import PermissionError, ToolError


class ToolPermission(StrEnum):
    """Permission class a tool requires (mirrors the MCP permission model)."""

    READ = "read"
    ANALYZE = "analyze"
    WRITE = "write"
    EXECUTE = "execute"
    DESTRUCTIVE = "destructive"


@dataclasses.dataclass(frozen=True)
class ToolResult:
    """A structured, serializable tool result."""

    ok: bool
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str | None = None

    @classmethod
    def success(cls, data: dict[str, Any]) -> ToolResult:
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        return cls(ok=False, error=error)


@runtime_checkable
class Tool(Protocol):
    """A neutral tool contract, independent of any transport.

    ``schema`` is an opaque descriptor (e.g. a JSON-Schema-like mapping); it is
    not tied to MCP. ``permission`` is the class required to execute the tool.
    ``model_callable`` declares whether a model may *request* this tool through
    the controlled inference loop (Phase 9) — WRITE/EXECUTE/DESTRUCTIVE tools
    default to ``False``.
    """

    name: str
    description: str
    schema: dict[str, Any]
    permission: ToolPermission
    model_callable: bool

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given arguments."""
        ...


def require_permission(tool: Tool, granted: frozenset[ToolPermission]) -> None:
    """Raise :class:`PermissionError` if *tool* requires a permission not granted."""
    if tool.permission not in granted:
        raise PermissionError(
            f"tool {tool.name!r} requires {tool.permission.value!r} permission"
        )


def invoke(tool: Tool, arguments: dict[str, Any]) -> ToolResult:
    """Execute *tool* and normalize failures into :class:`ToolResult`."""
    try:
        return tool.execute(arguments)
    except PermissionError:
        raise
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 — tools may raise arbitrary errors
        return ToolResult.failure(f"{type(exc).__name__}: {exc}")
