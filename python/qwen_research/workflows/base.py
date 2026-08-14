"""Executable workflow contract.

A ``Workflow`` expresses ``start`` / ``continue`` / ``pause`` / ``resume`` /
``cancel``. Phase 1 defines the contract only; deep-research workflows are not
implemented.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from qwen_research.common.ids import SessionId, TaskId, WorkflowId
from qwen_research.common.serialization import serializable


class WorkflowStatus(StrEnum):
    """Lifecycle state of a workflow run."""

    STARTED = "started"
    RUNNING = "running"
    PAUSED = "paused"
    RESUMED = "resumed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowContext:
    """The context handed to a workflow for a single run."""

    workflow_id: WorkflowId
    task_id: TaskId
    session_id: SessionId
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)


@serializable
@dataclasses.dataclass(frozen=True)
class WorkflowResult:
    """The outcome of a workflow lifecycle operation."""

    status: WorkflowStatus
    workflow_id: WorkflowId
    task_id: TaskId
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class Workflow(Protocol):
    """An executable research workflow."""

    workflow_id: WorkflowId

    def start(self, context: WorkflowContext) -> WorkflowResult: ...
    def continue_(self, context: WorkflowContext) -> WorkflowResult: ...
    def pause(self, context: WorkflowContext) -> WorkflowResult: ...
    def resume(self, context: WorkflowContext) -> WorkflowResult: ...
    def cancel(self, context: WorkflowContext) -> WorkflowResult: ...
