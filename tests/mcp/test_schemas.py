"""MCP wire schemas — the authoritative tool schema surface.

These tests assert against the **actual** wire schemas the SDK exposes (via
``MCPServerApp.tool_catalog()``), not a parallel hand-written copy. This locks
the wire schema as the contract and guarantees the parameter types in
``schemas.py`` cannot drift from what the SDK actually sends over the wire.
"""

from __future__ import annotations

from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import PROFILES
from qwen_research.mcp.schemas import DEFAULT_TOOLS, TOOL_DESCRIPTIONS
from qwen_research.mcp.server import MCPServerApp
from qwen_research.research.runtime import InMemoryResearchRuntime


def _catalog() -> dict:
    return MCPServerApp(InMemoryResearchRuntime()).tool_catalog()


def test_default_tool_set() -> None:
    assert DEFAULT_TOOLS == (
        "get_session",
        "create_session",
        "execute_task",
        "continue_task",
        "get_task_state",
        "get_research_state",
        "search_corpus",
        "get_source",
        "get_project_memory",
        "get_research_memory",
        "get_open_questions",
        "save_research_memory",
    )


def test_required_fields_match_tool_contract() -> None:
    catalog = _catalog()
    assert catalog["get_session"]["input_schema"]["required"] == ["session_id"]
    assert catalog["execute_task"]["input_schema"]["required"] == ["description"]
    assert catalog["continue_task"]["input_schema"]["required"] == ["task_id"]
    assert catalog["get_task_state"]["input_schema"]["required"] == ["task_id"]
    assert catalog["get_research_state"]["input_schema"]["required"] == ["task_id"]
    assert catalog["search_corpus"]["input_schema"]["required"] == ["query"]
    assert catalog["get_source"]["input_schema"]["required"] == ["document_id"]
    assert catalog["save_research_memory"]["input_schema"]["required"] == ["content"]
    # create_session has no required args (all defaulted) → no "required" key.
    assert "required" not in catalog["create_session"]["input_schema"]


def test_retrieval_mode_enum_on_search_corpus() -> None:
    schema = _catalog()["search_corpus"]["input_schema"]
    mode = schema["properties"]["mode"]
    assert mode["enum"] == ["lexical", "semantic", "hybrid"]
    assert mode["default"] == "hybrid"


def test_wire_tools_match_default_set() -> None:
    assert sorted(_catalog()) == sorted(DEFAULT_TOOLS)


def test_every_tool_has_description_and_schema() -> None:
    for name, entry in _catalog().items():
        assert name in TOOL_DESCRIPTIONS
        assert entry["description"] == TOOL_DESCRIPTIONS[name]
        assert entry["input_schema"]["type"] == "object"


def test_mode_enum_matches_domain_operating_mode() -> None:
    schema = _catalog()["create_session"]["input_schema"]
    mode = schema["properties"]["mode"]
    assert mode["enum"] == [m.value for m in OperatingMode]
    assert mode["default"] == "studio_native"


def test_reasoning_profile_enum_matches_domain_profiles() -> None:
    schema = _catalog()["execute_task"]["input_schema"]
    profile = schema["properties"]["reasoning_profile"]
    assert profile["enum"] == list(PROFILES)
    assert profile["default"] == "DEEP"


def test_field_descriptions_flow_to_wire() -> None:
    catalog = _catalog()
    props = catalog["get_session"]["input_schema"]["properties"]
    assert props["session_id"]["description"] == "The session identifier."

    create = catalog["create_session"]["input_schema"]["properties"]
    assert create["project_id"]["description"] == "The project id for the session."
    assert create["mode"]["description"] == "The operating mode."
    assert "metadata" in create

    execute = catalog["execute_task"]["input_schema"]["properties"]
    assert execute["description"]["description"] == "The task description."
    assert "session_id" in execute
