"""Semantic retriever over the vector index."""

from __future__ import annotations

import dataclasses
import sqlite3
from time import monotonic

from qwen_research.domain.errors import VectorIndexUnavailable
from qwen_research.embeddings.base import EmbeddingProvider
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.filters import apply_filters
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievalMode,
    SearchOptions,
    SearchResult,
)
from qwen_research.vector.interface import VectorIndex


class SemanticRetriever:
    """Retrieves chunks by embedding similarity over the vector index.

    Because the vector backend has no native metadata filtering, this retriever
    **overfetches** candidates (``candidate_limit``), applies filters, and only
    then truncates to the final limit — so a metadata filter cannot silently
    destroy recall when the top candidates fall outside the filter.
    """

    def __init__(
        self,
        corpus_index: CorpusIndex,
        vector_index: VectorIndex,
        provider: EmbeddingProvider,
    ) -> None:
        self._corpus = corpus_index
        self._vector = vector_index
        self._provider = provider

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        options = options or SearchOptions()
        started = monotonic()
        final_limit = max(0, options.limit)
        if not query.strip():
            return SearchResult((), query, 0, 0, 0.0, RetrievalMode.SEMANTIC.value)

        info = self._provider.model_info()
        # The hashing provider cannot fail; a future provider (transformer,
        # remote) raises ``EmbeddingBackendUnavailable`` itself, which
        # propagates here. We do not wrap this call in a broad handler.
        vector = self._provider.embed_query(query)

        candidate_limit = options.semantic_candidate_limit()
        try:
            hits = self._vector.search(
                vector, model=info.model, version=info.version, limit=candidate_limit
            )
        except (sqlite3.Error, OSError) as exc:
            # A backend-level vector failure (missing/corrupt index, I/O) is a
            # recoverable outage; unexpected programming errors propagate.
            raise VectorIndexUnavailable(f"vector index unavailable: {exc}") from exc

        chunks = self._corpus.get_chunks_for_ids([h.chunk_id for h in hits])
        score_by_id = {h.chunk_id: h.score for h in hits}
        ranked = []
        for chunk in chunks:
            score = score_by_id[chunk.chunk_id]
            ranked.append(
                dataclasses.replace(
                    chunk,
                    score=score,
                    semantic_score=score,
                    retrieval_mode=RetrievalMode.SEMANTIC.value,
                )
            )

        # Filter (overfetch was applied upstream), then rank, then truncate.
        filtered = apply_filters(ranked, options)
        for rank, chunk in enumerate(filtered):
            filtered[rank] = dataclasses.replace(chunk, rank=rank)
        return SearchResult(
            chunks=tuple(filtered[:final_limit]),
            query=query,
            candidate_count=len(filtered),
            returned_count=min(len(filtered), final_limit),
            duration_ms=(monotonic() - started) * 1000,
            mode=RetrievalMode.SEMANTIC.value,
            semantic_available=True,
            lexical_available=False,
        )

    def get_document(self, document_id: str) -> DocumentView | None:
        return self._corpus.get_document(document_id)

    def stats(self) -> CorpusStats:
        return self._corpus.stats()

    def status(self) -> IndexStatus:
        return self._corpus.status()
