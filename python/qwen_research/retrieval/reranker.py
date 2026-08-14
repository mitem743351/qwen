"""Optional reranker boundary.

The hybrid retriever may apply a :class:`Reranker` after fusion. Phase 4 ships
only the :class:`NoOpReranker`; a lightweight local cross-encoder reranker can
be added later without changing the search APIs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.retrieval.models import RetrievedChunk


@runtime_checkable
class Reranker(Protocol):
    """Re-scores a ranked candidate list in place (returns a new ordering)."""

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoOpReranker:
    """Identity reranker: leaves order and scores unchanged."""

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks
