"""Internal Tool Registry contract."""

from __future__ import annotations

import pytest

from qwen_research.domain.errors import PermissionError
from qwen_research.tools.base import ToolPermission, ToolResult, invoke, require_permission
from qwen_research.tools.registry import DuplicateToolError, ToolRegistry, UnknownToolError


class EchoTool:
    name = "echo"
    description = "Echo arguments back."
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    permission = ToolPermission.READ
    model_callable = True

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult.success({"echo": arguments.get("value")})


def test_register_and_lookup() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    assert "echo" in registry
    assert registry.get("echo").name == "echo"


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(DuplicateToolError):
        registry.register(EchoTool())


def test_removal_and_unknown() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.unregister("echo")
    with pytest.raises(UnknownToolError):
        registry.get("echo")
    with pytest.raises(UnknownToolError):
        registry.unregister("echo")


def test_listing_is_sorted() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    assert registry.list() == ("echo",)


def test_permission_enforcement() -> None:
    tool = EchoTool()
    require_permission(tool, frozenset({ToolPermission.READ}))
    with pytest.raises(PermissionError):
        require_permission(tool, frozenset({ToolPermission.WRITE}))


def test_invoke_normalizes_failures() -> None:
    class BrokenTool:
        name = "broken"
        description = "raises"
        schema: dict = {}
        permission = ToolPermission.READ
        model_callable = True

        def execute(self, arguments: dict) -> ToolResult:
            raise RuntimeError("boom")

    result = invoke(BrokenTool(), {})
    assert result.ok is False
    assert "boom" in (result.error or "")
