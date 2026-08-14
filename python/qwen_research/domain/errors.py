"""Typed domain errors.

Every error carries a machine-readable ``category`` so callers can branch
without string matching. Error messages must never contain provider secrets or
sensitive context.

``PermissionError`` here is a domain error distinct from the builtin of the
same name; it is exported from this module's namespace only.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    DOMAIN = "domain"
    VALIDATION = "validation"
    STATE = "state"
    CAPABILITY = "capability"
    TOOL = "tool"
    WORKFLOW = "workflow"
    INFERENCE = "inference"
    PERMISSION = "permission"
    PERSISTENCE = "persistence"
    CONFIGURATION = "configuration"
    UNSUPPORTED = "unsupported"


class DomainError(Exception):
    """Base class for all domain-level errors."""

    category: ErrorCategory = ErrorCategory.DOMAIN

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """A domain object failed validation."""

    category = ErrorCategory.VALIDATION


class InvalidTransitionError(DomainError):
    """An illegal task-state or workflow-state transition was attempted."""

    category = ErrorCategory.STATE


class CapabilityError(DomainError):
    """A requested capability is unavailable (e.g. provider does not support it)."""

    category = ErrorCategory.CAPABILITY


class UnsupportedOperationError(DomainError):
    """A contract operation is intentionally not implemented yet.

    Used instead of a fake implementation that silently returns empty results.
    """

    category = ErrorCategory.UNSUPPORTED


class ToolError(DomainError):
    """A tool failed or misbehaved."""

    category = ErrorCategory.TOOL


class WorkflowError(DomainError):
    """A workflow failed or misbehaved."""

    category = ErrorCategory.WORKFLOW


class InferenceError(DomainError):
    """An inference invocation or negotiation failed."""

    category = ErrorCategory.INFERENCE


class PermissionError(DomainError):
    """An operation was denied by the permission model."""

    category = ErrorCategory.PERMISSION


class PersistenceError(DomainError):
    """A persistence layer operation failed."""

    category = ErrorCategory.PERSISTENCE


class ConfigurationError(DomainError):
    """Configuration is missing or invalid."""

    category = ErrorCategory.CONFIGURATION
