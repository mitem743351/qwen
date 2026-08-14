"""Lexical retriever (SQLite FTS5).

The lexical retriever is the stable retrieval foundation. It applies its
filters natively (in SQL) where possible, and raises
:class:`LexicalRetrievalUnavailable` for backend-level outages (corrupt/missing
database, I/O) so the hybrid retriever can degrade explicitly — never by
silently converting an unexpected programming error into zero hits.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from time import monotonic

from qwen_research.domain.errors import LexicalRetrievalUnavailable
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievalMode,
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
            date_from=options.date_range[0] if options.date_range else None,
            date_to=options.date_range[1] if options.date_range else None,
        )
        try:
            candidates = self._index.search(
                query,
                limit=max(0, options.limit),
                offset=0,
                filters=filters,
            )
        except (sqlite3.Error, OSError) as exc:
            raise LexicalRetrievalUnavailable(
                f"lexical backend unavailable: {exc}"
            ) from exc
        if options.minimum_score is not None:
            candidates = [c for c in candidates if c.score >= options.minimum_score]
        candidates = candidates[: max(0, options.limit)]
        chunks = tuple(
            dataclasses.replace(
                c,
                lexical_score=c.score,
                retrieval_mode=RetrievalMode.LEXICAL.value,
                rank=rank,
            )
            for rank, c in enumerate(candidates)
        )
        return SearchResult(
            chunks=chunks,
            query=query,
            candidate_count=len(chunks),
            returned_count=len(chunks),
            duration_ms=(monotonic() - started) * 1000,
            mode=RetrievalMode.LEXICAL.value,
            lexical_available=True,
            semantic_available=False,
        )

    def get_document(self, document_id: str) -> DocumentView | None:
        return self._index.get_document(document_id)

    def stats(self) -> CorpusStats:
        return self._index.stats()

    def status(self) -> IndexStatus:
        return self._index.status()
