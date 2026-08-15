"""Research orchestration layer (Phase 7).

Deterministic planning and workflow execution: classifies tasks, builds
structured resumable plans, and executes them through registered stage
executors that integrate retrieval, verification, computation, and memory —
without any model invocation.
"""

from qwen_research.orchestration.capabilities import (
    CapabilityRegistry,
    capability_registry_from_runtime,
)
from qwen_research.orchestration.engine import WorkflowEngine
from qwen_research.orchestration.models import (
    CompletionCriteria,
    ComputationSpec,
    EventType,
    PlanRequirements,
    ResearchCapability,
    ResearchPlan,
    ResearchStage,
    ResearchStatus,
    ResearchTask,
    ResearchTrajectory,
    RetryPolicy,
    RunStatus,
    StageResult,
    StageStatus,
    StageType,
    SynthesisDraft,
    SynthesisRequest,
    TaskComplexity,
    TaskType,
    WorkflowEvent,
    WorkflowGuardrails,
    WorkflowRun,
    is_terminal_run_status,
)
from qwen_research.orchestration.planning import ResearchPlanner
from qwen_research.orchestration.service import OrchestrationService
from qwen_research.orchestration.stages import StageExecutionContext, StageExecutor
from qwen_research.orchestration.store import OrchestrationStore

__all__ = [
    "CapabilityRegistry",
    "CompletionCriteria",
    "ComputationSpec",
    "EventType",
    "OrchestrationService",
    "OrchestrationStore",
    "PlanRequirements",
    "ResearchCapability",
    "ResearchPlan",
    "ResearchPlanner",
    "ResearchStage",
    "ResearchStatus",
    "ResearchTask",
    "ResearchTrajectory",
    "RetryPolicy",
    "RunStatus",
    "StageExecutor",
    "StageExecutionContext",
    "StageResult",
    "StageStatus",
    "StageType",
    "SynthesisDraft",
    "SynthesisRequest",
    "TaskComplexity",
    "TaskType",
    "WorkflowEngine",
    "WorkflowEvent",
    "WorkflowGuardrails",
    "WorkflowRun",
    "capability_registry_from_runtime",
    "is_terminal_run_status",
]
