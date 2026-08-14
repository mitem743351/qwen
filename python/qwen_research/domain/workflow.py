"""The Workflow domain descriptor.

This is a *value object* describing a named research workflow. The executable
workflow contract (``start``/``continue``/``pause``/``resume``/``cancel``)
lives in ``qwen_research.workflows``.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.ids import WorkflowId, new_id
from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class Workflow:
    """A named, versioned research workflow descriptor."""

    workflow_id: WorkflowId
    name: str
    version: int
    configuration: dict[str, str]

    @classmethod
    def create(
        cls, name: str, *, version: int = 1, configuration: dict[str, str] | None = None
    ) -> Workflow:
        return cls(
            workflow_id=WorkflowId(new_id("workflow")),
            name=name,
            version=version,
            configuration=dict(configuration or {}),
        )
