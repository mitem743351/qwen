"""Memory service — the application-level memory façade.

Wraps the memory store + retriever behind a small set of high-value operations
used by the Research Runtime and MCP. Provenance is explicit; project/session
isolation is enforced here.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.timestamps import utc_now
from qwen_research.memory.interfaces import MemoryStore
from qwen_research.memory.models import (
    MemoryOrigin,
    MemoryType,
    QuestionStatus,
    ResearchMemory,
    ResearchQuestion,
)
from qwen_research.memory.provenance import ProvenanceValidator
from qwen_research.memory.retriever import MemoryHit, MemoryRetriever


class MemoryService:
    """Provider-neutral, project-scoped memory operations.

    ``validator`` (optional) enforces research-derived provenance: when present
    and ``origin == RESEARCH``, every ``source_refs``/``evidence_refs``/
    ``claim_refs`` must resolve (project-scoped) **before** the write commits.
    """

    def __init__(self, store: MemoryStore, *, validator: ProvenanceValidator | None = None) -> None:
        self._store = store
        self._retriever = MemoryRetriever(store)
        self._validator = validator

    def initialize(self) -> None:
        self._store.initialize()

    def get_project_memory(self, project_id: str, *, limit: int = 10) -> list[MemoryHit]:
        return self._retriever.search(project_id, memory_type=MemoryType.PROJECT, limit=limit)

    def get_research_memory(
        self, project_id: str, query: str | None = None, *, limit: int = 10
    ) -> list[MemoryHit]:
        return self._retriever.search(
            project_id, query, memory_type=MemoryType.RESEARCH, limit=limit
        )

    def get_open_questions(self, project_id: str, *, limit: int = 5) -> list[ResearchQuestion]:
        return self._store.get_questions(project_id)[:limit]

    def search_memory(
        self, project_id: str, query: str | None = None, *, limit: int = 10
    ) -> list[MemoryHit]:
        return self._retriever.search(project_id, query, limit=limit)

    def save_research_memory(
        self,
        project_id: str,
        content: str,
        *,
        source_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        claim_refs: tuple[str, ...] = (),
        computation_refs: tuple[str, ...] = (),
        dataset_refs: tuple[str, ...] = (),
        status: str = "proposed",
        origin: MemoryOrigin = MemoryOrigin.RESEARCH,
        provenance: dict[str, str] | None = None,
    ) -> ResearchMemory:
        """Save research-derived memory with explicit provenance.

        Research-derived references are validated (project-scoped) before the
        write; an invalid reference raises :class:`ProvenanceError` and nothing
        is persisted (atomic). ``computation_refs`` must resolve to a persisted
        computation in the same project. User-originated metadata
        (``origin=USER``) is not subject to research provenance validation.
        """
        if origin is MemoryOrigin.RESEARCH and self._validator is not None:
            self._validator.validate(
                project_id,
                source_refs=source_refs,
                evidence_refs=evidence_refs,
                claim_refs=claim_refs,
                computation_refs=computation_refs,
            )
        memory = ResearchMemory.create(
            project_id,
            content,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            claim_refs=claim_refs,
            computation_refs=computation_refs,
            dataset_refs=dataset_refs,
            status=status,
            origin=origin,
            provenance=provenance,
        )
        self._store.save_research_memory(memory)
        return memory

    def save_open_question(
        self, project_id: str, question: str, *, priority: int = 0
    ) -> ResearchQuestion:
        q = ResearchQuestion.create(project_id, question, priority=priority)
        self._store.save_question(q)
        return q

    def update_question_status(
        self, project_id: str, question_id: str, status: QuestionStatus
    ) -> ResearchQuestion | None:
        for q in self._store.get_questions(project_id):
            if q.question_id == question_id:
                updated = dataclasses.replace(
                    q, status=status, version=q.version + 1, updated_at=utc_now()
                )
                self._store.update_question(updated)
                return updated
        return None
