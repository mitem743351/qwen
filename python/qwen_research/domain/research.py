"""Research planning and state objects.

``ResearchState`` is the resumable, *structured* workflow state — hypotheses,
claims, evidence references, decisions, unresolved questions, and artifact/
verification references. It never stores hidden chain-of-thought.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.ids import (
    ArtifactId,
    ClaimId,
    EvidenceId,
    TaskId,
    VerificationId,
)
from qwen_research.common.serialization import serializable
from qwen_research.domain.task import TaskStatus


@serializable
@dataclasses.dataclass(frozen=True)
class Hypothesis:
    """A working hypothesis under investigation."""

    text: str


@serializable
@dataclasses.dataclass(frozen=True)
class Decision:
    """An auditable decision and its rationale."""

    text: str
    rationale: str


@serializable
@dataclasses.dataclass(frozen=True)
class UnresolvedQuestion:
    """An open question that persists until resolved."""

    text: str


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchPlan:
    """A decomposed plan: ordered steps for the task."""

    steps: tuple[str, ...]
    rationale: str = ""


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchState:
    """Resumable structured workflow state for a task.

    Explicitly contains **no** hidden chain-of-thought — only the structured
    outcomes needed for continuation, auditing, and reproducibility.
    """

    task_id: TaskId
    current_stage: TaskStatus
    plan: ResearchPlan | None = None
    hypotheses: tuple[Hypothesis, ...] = ()
    claims: tuple[ClaimId, ...] = ()
    evidence_refs: tuple[EvidenceId, ...] = ()
    decisions: tuple[Decision, ...] = ()
    unresolved_questions: tuple[UnresolvedQuestion, ...] = ()
    artifact_refs: tuple[ArtifactId, ...] = ()
    verification_refs: tuple[VerificationId, ...] = ()
    continuation_state: str | None = None

    @classmethod
    def create(cls, task_id: TaskId, *, plan: ResearchPlan | None = None) -> ResearchState:
        return cls(task_id=task_id, current_stage=TaskStatus.PLANNED, plan=plan)
