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
    VERIFICATION = "verification"
    CLAIM = "claim"
    COMPUTATION = "computation"
    ORCHESTRATION = "orchestration"


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


class VerificationError(DomainError):
    """Base class for evidence-integrity / verification errors."""

    category = ErrorCategory.VERIFICATION


class ClaimNotFoundError(VerificationError):
    """A referenced claim does not exist (in the current project scope)."""

    category = ErrorCategory.CLAIM


class EvidenceNotFoundError(VerificationError):
    """A referenced evidence item does not exist."""


class ContradictionNotFoundError(VerificationError):
    """A referenced contradiction does not exist."""


class VerificationReportNotFoundError(VerificationError):
    """A referenced verification report does not exist."""


class VerificationConfigurationError(VerificationError):
    """The verification subsystem is misconfigured."""


class ComputationError(DomainError):
    """Base class for deterministic-computation errors."""

    category = ErrorCategory.COMPUTATION


class ComputationValidationError(ComputationError):
    """A computation request is invalid (bad operation, parameters, or profile)."""


class ComputationNotFoundError(ComputationError):
    """A referenced computation does not exist (in the current project scope)."""


class DatasetError(ComputationError):
    """A dataset reference cannot be resolved or read."""


class QueryValidationError(ComputationError):
    """A SQL query or structured query is unsafe or invalid."""


class ExecutionTimeoutError(ComputationError):
    """A computation exceeded its time limit."""


class ResourceLimitError(ComputationError):
    """A computation exceeded a resource limit (output/rows/memory/input)."""


class SandboxError(ComputationError):
    """A Python sandbox violation or escape attempt was detected."""


class ArtifactError(ComputationError):
    """A computation artifact could not be written or read."""


class ComputationConfigurationError(ComputationError):
    """The computation subsystem is misconfigured."""


class OrchestrationError(DomainError):
    """Base class for research-orchestration errors."""

    category = ErrorCategory.ORCHESTRATION


class ResearchTaskNotFoundError(OrchestrationError):
    """A referenced research task does not exist (in the current project scope)."""


class PlanNotFoundError(OrchestrationError):
    """A referenced research plan does not exist."""


class RunNotFoundError(OrchestrationError):
    """A referenced workflow run does not exist."""


class WorkflowExecutionError(OrchestrationError):
    """A workflow run could not be executed (blocking/unsupported capability)."""


class ProviderConfigurationError(InferenceError):
    """Provider configuration is invalid (e.g. missing credential/endpoint/model)."""


class ProviderCredentialError(ProviderConfigurationError):
    """A provider credential is missing or invalid.

    Never carries the credential value in its message.
    """


class ProviderAuthError(InferenceError):
    """Provider authentication failed (e.g. 401/403)."""


class ProviderRateLimitError(InferenceError):
    """Provider rate limit or quota was exceeded (e.g. 429)."""


class ProviderTimeoutError(InferenceError):
    """A provider request exceeded its timeout."""


class ProviderServerError(InferenceError):
    """Provider returned a retryable server error (5xx)."""


class ProviderUnavailableError(InferenceError):
    """Provider could not be reached (connection failure)."""


class ModelNotFoundError(InferenceError):
    """The provider API reported that the requested model does not exist."""


class UnknownModelError(InferenceError):
    """The requested model id is not in the (operator-overridable) model catalog.

    Distinct from :class:`ModelNotFoundError`: this is raised from static
    catalog knowledge, before any provider API call, when the catalog is the
    authority. Unknown models may still be usable when configuration permits
    (conservative capabilities), so this is raised only when the caller requires
    a known model.
    """


class ModelUnavailableError(InferenceError):
    """Base class: a model exists but is not available in this context."""


class ModelPlanUnavailableError(ModelUnavailableError):
    """The model exists but is not available under the configured plan."""


class ModelRegionUnavailableError(ModelUnavailableError):
    """The model exists but is not available in the configured region."""


class ModelEndpointUnavailableError(ModelUnavailableError):
    """The model exists but is not exposed by the configured endpoint/surface."""


class EndpointCapabilityError(InferenceError):
    """The configured endpoint/surface does not support a requested capability."""


class StructuredOutputError(InferenceError):
    """A required structured output could not be parsed/validated."""
