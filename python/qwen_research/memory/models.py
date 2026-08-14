"""Typed memory domain objects.

Memory is structured and categorized — never a generic key/value dump. Every
research-derived entry carries provenance; user/project metadata is explicitly
marked with an ``origin``. No hidden chain-of-thought is ever stored.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class MemoryType(StrEnum):
    SESSION = "session"
    PROJECT = "project"
    RESEARCH = "research"
    DECISION = "decision"
    QUESTION = "question"
    SOURCE = "source"


class QuestionStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    ANSWERED = "answered"
    BLOCKED = "blocked"
    DISMISSED = "dismissed"


class MemoryOrigin(StrEnum):
    USER = "user"
    RESEARCH = "research"


def _refs(value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(value or ())


@serializable
@dataclasses.dataclass(frozen=True)
class ProjectMemory:
    """Project-scoped, session-independent memory (goals, scope, sources, notes)."""

    memory_id: str
    project_id: str
    content: str
    provenance: dict[str, str]
    origin: MemoryOrigin
    created_at: datetime
    updated_at: datetime
    version: int
    status: str = "active"

    @classmethod
    def create(
        cls,
        project_id: str,
        content: str,
        *,
        origin: MemoryOrigin = MemoryOrigin.USER,
        provenance: dict[str, str] | None = None,
    ) -> ProjectMemory:
        now = utc_now()
        return cls(
            memory_id=new_id("pmem"),
            project_id=project_id,
            content=content,
            provenance=dict(provenance or {}),
            origin=origin,
            created_at=now,
            updated_at=now,
            version=1,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchMemory:
    """Durable research-derived knowledge (claims/conclusions) with provenance."""

    memory_id: str
    project_id: str
    content: str
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    status: str
    provenance: dict[str, str]
    origin: MemoryOrigin
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        project_id: str,
        content: str,
        *,
        source_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        claim_refs: tuple[str, ...] = (),
        status: str = "proposed",
        origin: MemoryOrigin = MemoryOrigin.RESEARCH,
        provenance: dict[str, str] | None = None,
    ) -> ResearchMemory:
        now = utc_now()
        return cls(
            memory_id=new_id("rmem"),
            project_id=project_id,
            content=content,
            source_refs=_refs(source_refs),
            evidence_refs=_refs(evidence_refs),
            claim_refs=_refs(claim_refs),
            status=status,
            provenance=dict(provenance or {}),
            origin=origin,
            created_at=now,
            updated_at=now,
            version=1,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class DecisionRecord:
    """A recorded decision with its reason and supporting references."""

    decision_id: str
    project_id: str
    session_id: str | None
    decision: str
    reason: str
    evidence_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    status: str
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        project_id: str,
        decision: str,
        reason: str,
        *,
        session_id: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        source_refs: tuple[str, ...] = (),
    ) -> DecisionRecord:
        now = utc_now()
        return cls(
            decision_id=new_id("decision"),
            project_id=project_id,
            session_id=session_id,
            decision=decision,
            reason=reason,
            evidence_refs=_refs(evidence_refs),
            source_refs=_refs(source_refs),
            status="active",
            created_at=now,
            updated_at=now,
            version=1,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ResearchQuestion:
    """An unresolved research question that persists until resolved."""

    question_id: str
    project_id: str
    question: str
    priority: int
    status: QuestionStatus
    related_claims: tuple[str, ...]
    related_sources: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        project_id: str,
        question: str,
        *,
        priority: int = 0,
        status: QuestionStatus = QuestionStatus.OPEN,
        related_claims: tuple[str, ...] = (),
        related_sources: tuple[str, ...] = (),
    ) -> ResearchQuestion:
        now = utc_now()
        return cls(
            question_id=new_id("question"),
            project_id=project_id,
            question=question,
            priority=priority,
            status=status,
            related_claims=_refs(related_claims),
            related_sources=_refs(related_sources),
            created_at=now,
            updated_at=now,
            version=1,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class SourceMemory:
    """User-maintained notes about an important source (no invented quality)."""

    source_id: str
    project_id: str
    importance: str | None
    reliability_notes: str | None
    topics: tuple[str, ...]
    citation_metadata: dict[str, str]
    user_annotations: dict[str, str]
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        project_id: str,
        source_id: str,
        *,
        importance: str | None = None,
        reliability_notes: str | None = None,
        topics: tuple[str, ...] = (),
        citation_metadata: dict[str, str] | None = None,
        user_annotations: dict[str, str] | None = None,
    ) -> SourceMemory:
        now = utc_now()
        return cls(
            source_id=source_id,
            project_id=project_id,
            importance=importance,
            reliability_notes=reliability_notes,
            topics=_refs(topics),
            citation_metadata=dict(citation_metadata or {}),
            user_annotations=dict(user_annotations or {}),
            created_at=now,
            updated_at=now,
            version=1,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class SessionMemoryItem:
    """Short-lived structured session context (hypotheses, objective, refs)."""

    memory_id: str
    session_id: str
    project_id: str
    kind: str
    content: dict[str, str]
    created_at: datetime
    updated_at: datetime
    version: int
    status: str = "active"

    @classmethod
    def create(
        cls,
        session_id: str,
        project_id: str,
        kind: str,
        content: dict[str, str],
    ) -> SessionMemoryItem:
        now = utc_now()
        return cls(
            memory_id=new_id("smem"),
            session_id=session_id,
            project_id=project_id,
            kind=kind,
            content=dict(content),
            created_at=now,
            updated_at=now,
            version=1,
        )
