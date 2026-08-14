"""Context assembly boundary.

Combines a request with bounded, provenance-bearing evidence, memory, and
verification summaries into a ``ResearchContext``. Phase 4 builds the *data
assembly boundary* only — no sophisticated model-context optimizer. All content
here is untrusted data; it never carries control-plane meaning.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from qwen_research.memory.models import ResearchQuestion
from qwen_research.memory.retriever import MemoryHit
from qwen_research.retrieval.models import RetrievedChunk
from qwen_research.verification.models import VerificationSummary


@dataclasses.dataclass(frozen=True)
class ResearchContext:
    """A bounded, provenance-bearing context for a research request."""

    query: str
    evidence: tuple[RetrievedChunk, ...]
    memories: tuple[MemoryHit, ...]
    open_questions: tuple[ResearchQuestion, ...]
    current_state: Any | None = None
    verification: tuple[VerificationSummary, ...] = ()


@dataclasses.dataclass(frozen=True)
class ContextBudget:
    """Conservative limits to avoid context explosion."""

    max_evidence_chunks: int = 10
    max_memory_items: int = 10
    max_open_questions: int = 5
    max_verification_summaries: int = 5


def build_context(
    query: str,
    *,
    evidence: list[RetrievedChunk] | None = None,
    memories: list[MemoryHit] | None = None,
    open_questions: list[ResearchQuestion] | None = None,
    verification: list[VerificationSummary] | None = None,
    current_state: Any | None = None,
    budget: ContextBudget | None = None,
) -> ResearchContext:
    """Assemble a bounded research context from evidence, memory, and questions."""
    budget = budget or ContextBudget()
    return ResearchContext(
        query=query,
        evidence=tuple((evidence or [])[: budget.max_evidence_chunks]),
        memories=tuple((memories or [])[: budget.max_memory_items]),
        open_questions=tuple((open_questions or [])[: budget.max_open_questions]),
        verification=tuple((verification or [])[: budget.max_verification_summaries]),
        current_state=current_state,
    )
