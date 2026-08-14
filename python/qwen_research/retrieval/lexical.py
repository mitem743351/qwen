"""Lexical retriever (SQLite FTS5).

Phase 3 implements lexical retrieval only. The :class:`Retriever` interface is
the seam where a future ``HybridRetriever`` (lexical + semantic + reranking)
will attach without changing the Research Runtime.
"""

from __future__ import annotations

from time import monotonic

from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievalMode,
    RetrievedChunk,
    SearchFilters,
    SearchOptions,
    SearchResult,
)


class LexicalRetriever:
    """Retrieves ranked chunks via the index's FTS5 search."""

    def __init__(self, index: CorpusIndex) -> None:
        self._index = index

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        options = options or SearchOptions()
        started = monotonic()
        filters = SearchFilters(
            roots=options.roots,
            document_types=options.document_types,
            path_prefix=options.path_prefix,
        )
        candidates = self._index.search(
            query,
            limit=max(0, options.limit),
            offset=0,
            filters=filters,
        )
        if options.minimum_score is not None:
            candidates = [c for c in candidates if c.score >= options.minimum_score]
        candidates = candidates[: max(0, options.limit)]
        chunks = tuple(
            _with_mode(c, RetrievalMode.LEXICAL, rank)
            for rank, c in enumerate(candidates)
        )
        return SearchResult(
            chunks=chunks,
            query=query,
            candidate_count=len(chunks),
            returned_count=len(chunks),
            duration_ms=(monotonic() - started) * 1000,
            mode=RetrievalMode.LEXICAL.value,
        )

    def get_document(self, document_id: str) -> DocumentView | None:
        return self._index.get_document(document_id)

    def stats(self) -> CorpusStats:
        return self._index.stats()

    def status(self) -> IndexStatus:
        return self._index.status()


def _with_mode(chunk: RetrievedChunk, mode: RetrievalMode, rank: int) -> RetrievedChunk:
    import dataclasses

    return dataclasses.replace(
        chunk,
        lexical_score=chunk.score if mode is RetrievalMode.LEXICAL else None,
        retrieval_mode=mode.value,
        rank=rank,
    )
