"""Shared test fixtures."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import WorkflowId
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.state import (
    InMemoryArtifactStore,
    InMemoryResearchStateStore,
    InMemorySessionStore,
    InMemoryTaskStore,
)
from qwen_research.workflows.base import WorkflowContext, WorkflowResult, WorkflowStatus
from qwen_research.workflows.registry import WorkflowRegistry

PLACEHOLDER_WORKFLOW_ID = WorkflowId("placeholder_workflow")


class PlaceholderWorkflow:
    """A no-op workflow demonstrating the lifecycle contract.

    It performs **no** research, retrieval, inference, or verification; it only
    exercises the workflow lifecycle. Used by the vertical-slice test.
    """

    workflow_id = PLACEHOLDER_WORKFLOW_ID

    def start(self, context: WorkflowContext) -> WorkflowResult:
        return WorkflowResult(
            status=WorkflowStatus.STARTED,
            workflow_id=self.workflow_id,
            task_id=context.task_id,
            data={"note": "placeholder workflow started (no real work)"},
        )

    def continue_(self, context: WorkflowContext) -> WorkflowResult:
        return WorkflowResult(
            status=WorkflowStatus.COMPLETED,
            workflow_id=self.workflow_id,
            task_id=context.task_id,
        )

    def pause(self, context: WorkflowContext) -> WorkflowResult:
        return WorkflowResult(
            status=WorkflowStatus.PAUSED,
            workflow_id=self.workflow_id,
            task_id=context.task_id,
        )

    def resume(self, context: WorkflowContext) -> WorkflowResult:
        return WorkflowResult(
            status=WorkflowStatus.RESUMED,
            workflow_id=self.workflow_id,
            task_id=context.task_id,
        )

    def cancel(self, context: WorkflowContext) -> WorkflowResult:
        return WorkflowResult(
            status=WorkflowStatus.CANCELLED,
            workflow_id=self.workflow_id,
            task_id=context.task_id,
        )


@pytest.fixture
def workflow_registry() -> WorkflowRegistry:
    registry = WorkflowRegistry()
    registry.register(PlaceholderWorkflow())
    return registry


@pytest.fixture
def runtime(workflow_registry: WorkflowRegistry) -> InMemoryResearchRuntime:
    return InMemoryResearchRuntime(
        session_store=InMemorySessionStore(),
        task_store=InMemoryTaskStore(),
        state_store=InMemoryResearchStateStore(),
        artifact_store=InMemoryArtifactStore(),
        workflow_registry=workflow_registry,
    )
