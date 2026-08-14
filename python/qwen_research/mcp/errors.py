"""Error normalization for the MCP boundary.

Maps internal domain errors to safe external errors. Never exposes stack
traces, secrets, API keys, filesystem internals, provider credentials, or
hidden chain-of-thought.

This module is deliberately free of the MCP SDK so the mapping is unit-testable
in isolation; :mod:`qwen_research.mcp.server` converts the result into an
SDK ``MCPError``.
"""

from __future__ import annotations

import dataclasses

from qwen_research.domain.errors import (
    CapabilityError,
    ConfigurationError,
    DomainError,
    InferenceError,
    InvalidTransitionError,
    PermissionError,
    PersistenceError,
    ToolError,
    UnsupportedOperationError,
    ValidationError,
    WorkflowError,
)

# Standard JSON-RPC error codes (mirror the MCP protocol values).
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclasses.dataclass(frozen=True)
class MCPErrorInfo:
    """A safe, external error: a JSON-RPC code, a message, and a category."""

    code: int
    message: str
    category: str


def map_error(exc: Exception) -> MCPErrorInfo:
    """Map an internal exception to a safe external error.

    Client-correctable errors (validation, invalid state, permission) map to
    ``INVALID_PARAMS``; operational failures map to ``INTERNAL_ERROR``. The
    message is a safe, category-qualified description — never a traceback and
    never sensitive data.
    """
    if isinstance(exc, (ValidationError, InvalidTransitionError)):
        return MCPErrorInfo(INVALID_PARAMS, f"invalid arguments: {exc.message}", exc.category.value)
    if isinstance(exc, PermissionError):
        return MCPErrorInfo(INVALID_PARAMS, f"permission denied: {exc.message}", exc.category.value)
    if isinstance(exc, UnsupportedOperationError):
        return MCPErrorInfo(
            INTERNAL_ERROR, f"capability unavailable: {exc.message}", exc.category.value
        )
    if isinstance(
        exc,
        (
            CapabilityError,
            ConfigurationError,
            InferenceError,
            PersistenceError,
            ToolError,
            WorkflowError,
        ),
    ):
        return MCPErrorInfo(INTERNAL_ERROR, exc.message, exc.category.value)
    if isinstance(exc, DomainError):
        return MCPErrorInfo(INTERNAL_ERROR, exc.message, exc.category.value)
    return MCPErrorInfo(INTERNAL_ERROR, "internal error", "domain")
