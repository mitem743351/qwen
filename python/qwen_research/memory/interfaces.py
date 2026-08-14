"""Neutral memory repository interfaces.

The Research Runtime depends on these protocols; SQL lives only inside the
repository implementation. Isolation (project/session scoping) is enforced at
these query boundaries, not by prompts.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.memory.models import (
    DecisionRecord,
    ProjectMemory,
    ResearchMemory,
    ResearchQuestion,
    SessionMemoryItem,
    SourceMemory,
)


@runtime_checkable
class SessionMemoryRepository(Protocol):
    def save_session_item(self, item: SessionMemoryItem) -> None: ...
    def get_session_items(self, session_id: str) -> list[SessionMemoryItem]: ...


@runtime_checkable
class ProjectMemoryRepository(Protocol):
    def save_project_memory(self, memory: ProjectMemory) -> None: ...
    def get_project_memory(self, project_id: str) -> list[ProjectMemory]: ...


@runtime_checkable
class ResearchMemoryRepository(Protocol):
    def save_research_memory(self, memory: ResearchMemory) -> None: ...
    def get_research_memory(self, project_id: str) -> list[ResearchMemory]: ...


@runtime_checkable
class DecisionRepository(Protocol):
    def save_decision(self, decision: DecisionRecord) -> None: ...
    def get_decisions(self, project_id: str) -> list[DecisionRecord]: ...


@runtime_checkable
class QuestionRepository(Protocol):
    def save_question(self, question: ResearchQuestion) -> None: ...
    def get_questions(self, project_id: str) -> list[ResearchQuestion]: ...
    def update_question(self, question: ResearchQuestion) -> None: ...


@runtime_checkable
class SourceMemoryRepository(Protocol):
    def save_source_memory(self, memory: SourceMemory) -> None: ...

    def get_source_memory(
        self, project_id: str, source_id: str | None = None
    ) -> list[SourceMemory]: ...


@runtime_checkable
class MemoryStore(
    SessionMemoryRepository,
    ProjectMemoryRepository,
    ResearchMemoryRepository,
    DecisionRepository,
    QuestionRepository,
    SourceMemoryRepository,
    Protocol,
):
    """A store that implements all six memory repositories."""

    def initialize(self) -> None: ...
    def close(self) -> None: ...
