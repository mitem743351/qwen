"""Domain model: stable, transport- and provider-independent contracts.

The domain layer is the shared contract used by the MCP Server (future), the
Research Runtime, and the Inference Runtime. It must never import MCP, Qwen,
HTTP, or database specifics.
"""

from qwen_research.domain.artifact import Artifact, ArtifactType
from qwen_research.domain.claim import Claim, ClaimStatus
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
from qwen_research.domain.evidence import Evidence
from qwen_research.domain.inference import (
    CapabilityClass,
    EmulationDirective,
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    ModelInfo,
    NegotiationDecision,
    NegotiationOutcome,
    NegotiationResult,
    ProviderCapabilities,
    ProviderLimits,
    WorkflowEmulationPlan,
    negotiate,
)
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import (
    DEEP,
    EXTREME,
    FAST,
    NORMAL,
    PROFILES,
    XHIGH,
    ContinuationPolicy,
    ParallelismMode,
    ReasoningBudget,
    ReasoningProfile,
    get_profile,
)
from qwen_research.domain.research import (
    Decision,
    Hypothesis,
    ResearchPlan,
    ResearchState,
    UnresolvedQuestion,
)
from qwen_research.domain.session import Session
from qwen_research.domain.source import Source, SourceType
from qwen_research.domain.task import (
    CONTROL_STATES,
    EXECUTION_STATES,
    TERMINAL_STATES,
    Task,
    TaskStatus,
    is_control_state,
    is_execution_state,
    is_terminal_state,
)
from qwen_research.domain.verification import VerificationResult, VerificationStatus
from qwen_research.domain.workflow import Workflow

__all__ = [
    "Artifact",
    "ArtifactType",
    "CapabilityClass",
    "CapabilityError",
    "Claim",
    "ClaimStatus",
    "ConfigurationError",
    "CONTROL_STATES",
    "ContinuationPolicy",
    "DEEP",
    "Decision",
    "DomainError",
    "EmulationDirective",
    "EXECUTION_STATES",
    "EXTREME",
    "Evidence",
    "FAST",
    "Hypothesis",
    "InferenceError",
    "InferencePolicy",
    "InferenceRequest",
    "InferenceResult",
    "InvalidTransitionError",
    "is_control_state",
    "is_execution_state",
    "is_terminal_state",
    "ModelInfo",
    "NegotiationDecision",
    "NegotiationOutcome",
    "NegotiationResult",
    "NORMAL",
    "OperatingMode",
    "ParallelismMode",
    "PermissionError",
    "PersistenceError",
    "PROFILES",
    "ProviderCapabilities",
    "ProviderLimits",
    "ReasoningBudget",
    "ReasoningProfile",
    "get_profile",
    "ResearchPlan",
    "ResearchState",
    "Session",
    "Source",
    "SourceType",
    "Task",
    "TaskStatus",
    "TERMINAL_STATES",
    "ToolError",
    "UnresolvedQuestion",
    "UnsupportedOperationError",
    "ValidationError",
    "VerificationResult",
    "VerificationStatus",
    "Workflow",
    "WorkflowEmulationPlan",
    "WorkflowError",
    "XHIGH",
    "negotiate",
]
