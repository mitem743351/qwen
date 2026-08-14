"""Structured memory retrieval.

Phase 4 uses lexical/structured retrieval over memory (no automatic embedding of
all memory). Queries are scoped by project (isolation) and optionally by
session, memory type, and question status.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from qwen_research.memory.interfaces import MemoryStore
from qwen_research.memory.models import MemoryType, QuestionStatus


@dataclasses.dataclass(frozen=True)
class MemoryHit:
    """A single matched memory record, flattened for context assembly."""

    memory_type: MemoryType
    memory_id: str
    project_id: str
    session_id: str | None
    content: str
    refs: tuple[str, ...]
    status: str
    created_at: datetime
    score: float


class MemoryRetriever:
    """Finds relevant structured memory for a task (bounded, project-scoped)."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def search(
        self,
        project_id: str,
        query: str | None = None,
        *,
        memory_type: MemoryType | None = None,
        status: str | None = None,
        limit: int = 10,
    ) -> list[MemoryHit]:
        """Return a ranked, filtered, project-scoped set of memory hits."""
        q = (query or "").strip().lower()
        hits: list[MemoryHit] = []

        if memory_type is None or memory_type is MemoryType.PROJECT:
            for pm in self._store.get_project_memory(project_id):
                hits.append(
                    _hit(
                        MemoryType.PROJECT, pm.memory_id, project_id, None,
                        pm.content, (), pm.status, pm.created_at, _score(q, pm.content),
                    )
                )

        if memory_type is None or memory_type is MemoryType.RESEARCH:
            for rm in self._store.get_research_memory(project_id):
                refs = rm.source_refs + rm.evidence_refs + rm.claim_refs
                hits.append(
                    _hit(
                        MemoryType.RESEARCH, rm.memory_id, project_id, None,
                        rm.content, refs, rm.status, rm.created_at, _score(q, rm.content),
                    )
                )

        if memory_type is None or memory_type is MemoryType.DECISION:
            for d in self._store.get_decisions(project_id):
                hits.append(
                    _hit(
                        MemoryType.DECISION, d.decision_id, project_id, d.session_id,
                        d.decision, d.evidence_refs + d.source_refs, d.status,
                        d.created_at, _score(q, d.decision + " " + d.reason),
                    )
                )

        if memory_type is None or memory_type is MemoryType.QUESTION:
            for qq in self._store.get_questions(project_id):
                if status is not None and qq.status.value != status:
                    continue
                hits.append(
                    _hit(
                        MemoryType.QUESTION, qq.question_id, project_id, None,
                        qq.question, qq.related_claims + qq.related_sources,
                        qq.status.value, qq.created_at, _score(q, qq.question),
                    )
                )

        if memory_type is None or memory_type is MemoryType.SOURCE:
            for s in self._store.get_source_memory(project_id):
                content = " ".join(filter(None, [s.importance, s.reliability_notes, *s.topics]))
                hits.append(
                    _hit(
                        MemoryType.SOURCE, s.source_id, project_id, None,
                        content, (), "active", s.created_at, _score(q, content),
                    )
                )

        if memory_type is not None:
            hits = [h for h in hits if h.memory_type is memory_type]
        hits.sort(key=lambda h: (-h.score, h.created_at.isoformat(), h.memory_id))
        return hits[: max(0, limit)]

    def open_questions(
        self,
        project_id: str,
        *,
        status: QuestionStatus | None = None,
        limit: int = 5,
    ) -> list[MemoryHit]:
        return self.search(
            project_id,
            memory_type=MemoryType.QUESTION,
            status=status.value if status else None,
            limit=limit,
        )


def _hit(
    memory_type: MemoryType,
    memory_id: str,
    project_id: str,
    session_id: str | None,
    content: str,
    refs: tuple[str, ...],
    status: str,
    created_at: datetime,
    score: float,
) -> MemoryHit:
    return MemoryHit(
        memory_type=memory_type,
        memory_id=memory_id,
        project_id=project_id,
        session_id=session_id,
        content=content,
        refs=tuple(refs),
        status=status,
        created_at=created_at,
        score=score,
    )


def _score(query: str, text: str) -> float:
    if not query:
        return 0.0
    return 1.0 if query in text.lower() else 0.0
