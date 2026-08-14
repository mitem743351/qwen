"""In-memory repository implementations.

These satisfy the persistence contracts for Phase 1 tests and the minimal
vertical slice. They hold live object references only; real durability is a
later phase.
"""

from __future__ import annotations

from qwen_research.common.ids import ArtifactId, SessionId, TaskId
from qwen_research.domain.artifact import Artifact
from qwen_research.domain.research import ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[SessionId, Session] = {}

    def save(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: SessionId) -> Session | None:
        return self._sessions.get(session_id)


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[TaskId, Task] = {}

    def save(self, task: Task) -> None:
        self._tasks[task.task_id] = task

    def get(self, task_id: TaskId) -> Task | None:
        return self._tasks.get(task_id)


class InMemoryResearchStateStore:
    def __init__(self) -> None:
        self._states: dict[TaskId, ResearchState] = {}

    def save(self, state: ResearchState) -> None:
        self._states[state.task_id] = state

    def get(self, task_id: TaskId) -> ResearchState | None:
        return self._states.get(task_id)


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._artifacts: dict[ArtifactId, Artifact] = {}

    def save(self, artifact: Artifact) -> None:
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: ArtifactId) -> Artifact | None:
        return self._artifacts.get(artifact_id)
