"""Workflow Registry and workflow lifecycle contract."""

from __future__ import annotations

import pytest

from conftest import PLACEHOLDER_WORKFLOW_ID, PlaceholderWorkflow
from qwen_research.common.ids import SessionId, TaskId, WorkflowId
from qwen_research.workflows.base import WorkflowContext, WorkflowStatus
from qwen_research.workflows.registry import (
    DuplicateWorkflowError,
    UnknownWorkflowError,
    WorkflowRegistry,
)

_TASK = TaskId("task_1")
_SESSION = SessionId("session_1")


def _context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id=PLACEHOLDER_WORKFLOW_ID, task_id=_TASK, session_id=_SESSION
    )


def test_register_and_lookup() -> None:
    registry = WorkflowRegistry()
    registry.register(PlaceholderWorkflow())
    assert PLACEHOLDER_WORKFLOW_ID in registry
    assert registry.get(PLACEHOLDER_WORKFLOW_ID).workflow_id == PLACEHOLDER_WORKFLOW_ID


def test_duplicate_registration_raises() -> None:
    registry = WorkflowRegistry()
    registry.register(PlaceholderWorkflow())
    with pytest.raises(DuplicateWorkflowError):
        registry.register(PlaceholderWorkflow())


def test_unknown_workflow_raises() -> None:
    registry = WorkflowRegistry()
    with pytest.raises(UnknownWorkflowError):
        registry.get(WorkflowId("missing"))
    with pytest.raises(UnknownWorkflowError):
        registry.unregister(WorkflowId("missing"))


def test_lifecycle_contract() -> None:
    registry = WorkflowRegistry()
    workflow = PlaceholderWorkflow()
    registry.register(workflow)

    assert workflow.start(_context()).status is WorkflowStatus.STARTED
    assert workflow.pause(_context()).status is WorkflowStatus.PAUSED
    assert workflow.resume(_context()).status is WorkflowStatus.RESUMED
    assert workflow.continue_(_context()).status is WorkflowStatus.COMPLETED
    assert workflow.cancel(_context()).status is WorkflowStatus.CANCELLED
