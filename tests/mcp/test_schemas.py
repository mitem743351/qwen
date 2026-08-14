"""MCP tool schema definitions."""

from __future__ import annotations

from qwen_research.mcp.schemas import DEFAULT_TOOLS, TOOL_DESCRIPTIONS, TOOL_SCHEMAS


def test_default_tool_set() -> None:
    assert DEFAULT_TOOLS == (
        "get_session",
        "create_session",
        "execute_task",
        "continue_task",
        "get_task_state",
        "get_research_state",
    )


def test_every_default_tool_has_schema_and_description() -> None:
    for name in DEFAULT_TOOLS:
        assert name in TOOL_SCHEMAS
        assert name in TOOL_DESCRIPTIONS
        assert TOOL_DESCRIPTIONS[name]


def test_schemas_are_objects_with_required_fields() -> None:
    for schema in TOOL_SCHEMAS.values():
        assert schema["type"] == "object"
        assert "properties" in schema
        # required is present (possibly empty) for every schema.
        assert "required" in schema


def test_required_fields_match_tool_contract() -> None:
    assert TOOL_SCHEMAS["get_session"]["required"] == ["session_id"]
    assert TOOL_SCHEMAS["execute_task"]["required"] == ["description"]
    assert TOOL_SCHEMAS["continue_task"]["required"] == ["task_id"]
    assert TOOL_SCHEMAS["get_task_state"]["required"] == ["task_id"]
    assert TOOL_SCHEMAS["get_research_state"]["required"] == ["task_id"]
    # create_session has no required args (all defaulted).
    assert TOOL_SCHEMAS["create_session"]["required"] == []


def test_mode_enum_in_create_session_schema() -> None:
    mode = TOOL_SCHEMAS["create_session"]["properties"]["mode"]
    assert mode["enum"] == ["studio_native", "gateway_inference", "hybrid"]


def test_reasoning_profile_enum_in_execute_task_schema() -> None:
    profile = TOOL_SCHEMAS["execute_task"]["properties"]["reasoning_profile"]
    assert profile["enum"] == ["FAST", "NORMAL", "DEEP", "XHIGH", "EXTREME"]
