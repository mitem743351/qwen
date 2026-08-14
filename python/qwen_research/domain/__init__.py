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
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    ModelInfo,
    NegotiationOutcome,
    ProviderCapabilities,
    negotiate,
)
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import (
    DEEP,
    EXTREME,
    FAST,
    NORMAL,
    XHIGH,
    ContinuationPolicy,
    ParallelismMode,
    ReasoningBudget,
    ReasoningProfile,
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
    "CapabilityError",
    "Claim",
    "ClaimStatus",
    "ConfigurationError",
    "CONTROL_STATES",
    "ContinuationPolicy",
    "DEEP",
    "Decision",
    "DomainError",
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
    "NORMAL",
    "NegotiationOutcome",
    "OperatingMode",
    "ParallelismMode",
    "PermissionError",
    "PersistenceError",
    "ProviderCapabilities",
    "ReasoningBudget",
    "ReasoningProfile",
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
    "WorkflowError",
    "XHIGH",
    "negotiate",
]
