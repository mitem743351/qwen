"""The Workflow Registry."""

from __future__ import annotations

from qwen_research.common.ids import WorkflowId
from qwen_research.domain.errors import WorkflowError
from qwen_research.workflows.base import Workflow


class DuplicateWorkflowError(WorkflowError):
    """Raised when registering a workflow id that is already present."""


class UnknownWorkflowError(WorkflowError):
    """Raised when looking up a workflow that is not registered."""


class WorkflowRegistry:
    """A registry of :class:`Workflow` implementations keyed by workflow id."""

    def __init__(self) -> None:
        self._workflows: dict[WorkflowId, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        if workflow.workflow_id in self._workflows:
            raise DuplicateWorkflowError(
                f"workflow {workflow.workflow_id!r} is already registered"
            )
        self._workflows[workflow.workflow_id] = workflow

    def unregister(self, workflow_id: WorkflowId) -> Workflow:
        try:
            return self._workflows.pop(workflow_id)
        except KeyError:
            raise UnknownWorkflowError(
                f"workflow {workflow_id!r} is not registered"
            ) from None

    def get(self, workflow_id: WorkflowId) -> Workflow:
        try:
            return self._workflows[workflow_id]
        except KeyError:
            raise UnknownWorkflowError(
                f"workflow {workflow_id!r} is not registered"
            ) from None

    def list(self) -> tuple[WorkflowId, ...]:
        return tuple(sorted(self._workflows))

    def __contains__(self, workflow_id: object) -> bool:
        return workflow_id in self._workflows
