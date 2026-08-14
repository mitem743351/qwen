"""Minimal vertical slice: the full local flow with no Qwen/MCP/network/corpus."""

from __future__ import annotations

from conftest import PLACEHOLDER_WORKFLOW_ID
from qwen_research.common.serialization import dumps
from qwen_research.domain.artifact import Artifact, ArtifactType
from qwen_research.domain.reasoning import DEEP
from qwen_research.domain.task import TaskStatus
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.workflows.base import WorkflowStatus


def test_vertical_slice(runtime: InMemoryResearchRuntime) -> None:
    # 1. create session
    session = runtime.create_session()
    assert session.session_id

    # 2. create + classify + plan task (execute_task does all three)
    task = runtime.execute_task("Research question?", profile=DEEP, session_id=session.session_id)
    assert task.status is TaskStatus.PLANNED

    # 3. reasoning profile selected
    assert task.reasoning_profile == "DEEP"

    # 4. research state created
    state = runtime.get_state(task.task_id)
    assert state.plan is not None
    assert state.current_stage is TaskStatus.PLANNED

    # 5. execute a placeholder workflow
    result = runtime.run_workflow(PLACEHOLDER_WORKFLOW_ID, task.task_id)
    assert result.status is WorkflowStatus.STARTED

    # 6. transition through valid states
    while not task.is_terminal:
        task = runtime.continue_task(task.task_id)
    assert task.status is TaskStatus.COMPLETED

    # 7. produce a placeholder artifact
    artifact = Artifact.create(
        ArtifactType.REPORT,
        "out/report.md",
        task_id=task.task_id,
        session_id=session.session_id,
        provenance={"workflow": "placeholder"},
    )
    saved = runtime.save_artifact(artifact)
    assert saved.artifact_id == artifact.artifact_id

    # 8. serialize final state
    state = runtime.get_state(task.task_id)
    assert state.current_stage is TaskStatus.COMPLETED
    assert artifact.artifact_id in state.artifact_refs
    serialized = dumps(state)
    assert "chain_of_thought" not in serialized
    assert '"schema_version": 1' in serialized
