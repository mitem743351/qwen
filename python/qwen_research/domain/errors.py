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
    CORPUS = "corpus"
    SECURITY = "security"
    DOCUMENT = "document"
    INDEX = "index"
    RETRIEVAL = "retrieval"
    PROVENANCE = "provenance"


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


class CorpusError(DomainError):
    """Base class for corpus-level errors."""

    category = ErrorCategory.CORPUS


class PathSecurityError(CorpusError):
    """A filesystem request would escape the configured corpus roots.

    The message never contains the offending absolute path.
    """

    category = ErrorCategory.SECURITY


class UnsupportedDocumentError(CorpusError):
    """A file's type is not supported by any registered parser."""

    category = ErrorCategory.DOCUMENT


class DocumentParseError(CorpusError):
    """A document could not be parsed (but the file was discovered)."""

    category = ErrorCategory.DOCUMENT


class DocumentNotFoundError(CorpusError):
    """A requested document is not present in the index."""

    category = ErrorCategory.DOCUMENT


class CorpusIndexError(CorpusError):
    """The corpus index is missing, uninitialized, or in a bad state.

    Named ``CorpusIndexError`` rather than ``IndexError`` to avoid shadowing
    the builtin ``IndexError``.
    """

    category = ErrorCategory.INDEX


class RetrievalError(DomainError):
    """Base class for retrieval failures."""

    category = ErrorCategory.RETRIEVAL


class RetrievalBackendUnavailable(RetrievalError):  # noqa: N818
    """A retrieval backend is unavailable (a recoverable, expected outage).

    This is **not** a programming error: it represents a backend that is
    legitimately missing/broken (e.g. the vector index is absent or the corpus
    database is corrupt). Hybrid retrieval may fall back to the other backend;
    unexpected exceptions (TypeError, logic bugs, …) must **not** be conflated
    with this.
    """


class SemanticRetrievalUnavailable(RetrievalBackendUnavailable):  # noqa: N818
    """The semantic (embedding/vector) backend is unavailable."""


class VectorIndexUnavailable(SemanticRetrievalUnavailable):  # noqa: N818
    """The vector index backend is unavailable."""


class EmbeddingBackendUnavailable(SemanticRetrievalUnavailable):  # noqa: N818
    """The embedding provider backend is unavailable."""


class LexicalRetrievalUnavailable(RetrievalBackendUnavailable):  # noqa: N818
    """The lexical (FTS) backend is unavailable."""


class RetrievalQueryError(RetrievalError):
    """A retrieval query is invalid."""


class RetrievalConfigurationError(RetrievalError):
    """Retrieval is misconfigured."""


class ProvenanceError(DomainError):
    """A research-memory reference does not resolve.

    ``kind`` is the reference category (``source``/``evidence``/``claim``) and
    ``identifier`` is the offending reference id. The message identifies the
    category and id without leaking unrelated private information.
    """

    category = ErrorCategory.PROVENANCE

    def __init__(self, kind: str, identifier: str) -> None:
        self.kind = kind
        self.identifier = identifier
        super().__init__(f"unresolved {kind} reference: {identifier}")
