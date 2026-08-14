"""Repository interfaces (protocols) for durable state.

These are abstract storage contracts. The domain layer does not depend on any
concrete backend; implementations are chosen at configuration time. Phase 1
provides in-memory implementations only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.common.ids import ArtifactId, SessionId, TaskId
from qwen_research.domain.artifact import Artifact
from qwen_research.domain.research import ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task


@runtime_checkable
class SessionRepository(Protocol):
    def save(self, session: Session) -> None: ...
    def get(self, session_id: SessionId) -> Session | None: ...


@runtime_checkable
class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...
    def get(self, task_id: TaskId) -> Task | None: ...


@runtime_checkable
class ResearchStateRepository(Protocol):
    def save(self, state: ResearchState) -> None: ...
    def get(self, task_id: TaskId) -> ResearchState | None: ...


@runtime_checkable
class ArtifactRepository(Protocol):
    def save(self, artifact: Artifact) -> None: ...
    def get(self, artifact_id: ArtifactId) -> Artifact | None: ...
