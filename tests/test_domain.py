"""Domain object construction, validation, and value semantics."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import SessionId, TaskId
from qwen_research.common.serialization import dumps, loads
from qwen_research.domain.artifact import Artifact, ArtifactType
from qwen_research.domain.claim import Claim, ClaimStatus
from qwen_research.domain.evidence import Evidence
from qwen_research.domain.reasoning import DEEP
from qwen_research.domain.session import Session
from qwen_research.domain.source import Source, SourceType
from qwen_research.domain.task import Task, TaskStatus
from qwen_research.domain.workflow import Workflow


def test_task_construction() -> None:
    session_id = SessionId("session_abc")
    task = Task.create("Investigate X", session_id, "DEEP")
    assert task.status is TaskStatus.CREATED
    assert task.task_id.startswith("task_")
    assert task.session_id == session_id
    assert task.reasoning_profile == "DEEP"


def test_task_is_frozen_and_value_like() -> None:
    task = Task.create("t", SessionId("s"), "FAST")
    moved = task.transition(TaskStatus.CLASSIFIED)
    assert task.status is TaskStatus.CREATED  # original unchanged
    assert moved.status is TaskStatus.CLASSIFIED
    assert moved.task_id == task.task_id
    with pytest.raises(AttributeError):
        task.status = TaskStatus.COMPLETED  # type: ignore[misc]


def test_session_construction() -> None:
    session = Session.create()
    assert session.session_id.startswith("session_")
    assert session.project_id == "default"


def test_source_and_evidence() -> None:
    source = Source.create("https://example.com/doc", "Doc", SourceType.PAPER)
    evidence = Evidence.create(source.source_id, "p.1", "excerpt text", relevance=0.9)
    assert evidence.source_id == source.source_id


def test_claim_confidence_validation() -> None:
    with pytest.raises(ValueError):
        Claim.create("claim", confidence=1.5)
    claim = Claim.create("claim", confidence=0.5)
    assert claim.status is ClaimStatus.PROPOSED


def test_artifact_construction() -> None:
    task_id = TaskId("task_1")
    artifact = Artifact.create(ArtifactType.REPORT, "out/report.md", task_id=task_id)
    assert artifact.task_id == task_id
    assert artifact.version == 1


def test_workflow_descriptor() -> None:
    workflow = Workflow.create("deep-research", version=2)
    assert workflow.workflow_id.startswith("workflow_")
    assert workflow.version == 2


def test_domain_objects_serialize_roundtrip() -> None:
    session = Session.create()
    task = Task.create("Q", session.session_id, DEEP.name)
    state_objects = [session, task, Source.create("u", "t", SourceType.NOTE)]
    for obj in state_objects:
        assert loads(dumps(obj)) == obj


def test_serialization_has_no_chain_of_thought_field() -> None:
    task = Task.create("Q", SessionId("s"), "DEEP")
    payload = dumps(task)
    assert "chain_of_thought" not in payload
    assert "thinking" not in payload.lower()
