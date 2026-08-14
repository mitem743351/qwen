"""MCP tool input schemas and descriptions.

Declarative JSON-Schema dictionaries and human-readable descriptions for the
Phase 2 minimal tool set. These are the *semantic authority* for the MCP tool
surface; the internal domain contracts remain the source of truth for behavior
(see :mod:`qwen_research.mcp.adapters` for the conversion boundary).
"""

from __future__ import annotations

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_session": "Return a session by its session id.",
    "create_session": (
        "Create a new research session. Optionally specify a project id and "
        "operating mode; defaults to project 'default' and mode 'studio_native'."
    ),
    "execute_task": (
        "Create, classify, and plan a research task, optionally within an "
        "existing session and under a named reasoning profile."
    ),
    "continue_task": "Advance a task one step along its execution progression.",
    "get_task_state": "Return the current state of a task.",
    "get_research_state": "Return the structured research state of a task.",
}

GET_SESSION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string", "description": "The session identifier."},
    },
    "required": ["session_id"],
}

CREATE_SESSION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "default": "default"},
        "mode": {
            "type": "string",
            "enum": ["studio_native", "gateway_inference", "hybrid"],
            "default": "studio_native",
        },
        "metadata": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Optional string key/value metadata.",
        },
    },
    "required": [],
}

EXECUTE_TASK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "The task description."},
        "session_id": {
            "type": "string",
            "description": "Optional existing session id; a new session is created if omitted.",
        },
        "reasoning_profile": {
            "type": "string",
            "enum": ["FAST", "NORMAL", "DEEP", "XHIGH", "EXTREME"],
            "default": "DEEP",
        },
    },
    "required": ["description"],
}

CONTINUE_TASK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The task identifier."},
    },
    "required": ["task_id"],
}

GET_TASK_STATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The task identifier."},
    },
    "required": ["task_id"],
}

GET_RESEARCH_STATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The task identifier."},
    },
    "required": ["task_id"],
}

#: Tool name → input JSON schema (the MCP tool surface).
TOOL_SCHEMAS: dict[str, dict] = {
    "get_session": GET_SESSION_SCHEMA,
    "create_session": CREATE_SESSION_SCHEMA,
    "execute_task": EXECUTE_TASK_SCHEMA,
    "continue_task": CONTINUE_TASK_SCHEMA,
    "get_task_state": GET_TASK_STATE_SCHEMA,
    "get_research_state": GET_RESEARCH_STATE_SCHEMA,
}

#: The Phase 2 minimal tool set, in registration order.
DEFAULT_TOOLS: tuple[str, ...] = (
    "get_session",
    "create_session",
    "execute_task",
    "continue_task",
    "get_task_state",
    "get_research_state",
)
