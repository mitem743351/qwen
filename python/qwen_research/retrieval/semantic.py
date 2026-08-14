"""Semantic retriever over the vector index."""

from __future__ import annotations

import dataclasses
from time import monotonic

from qwen_research.embeddings.base import EmbeddingProvider
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievalMode,
    RetrievedChunk,
    SearchOptions,
    SearchResult,
)
from qwen_research.vector.interface import VectorIndex


class SemanticRetriever:
    """Retrieves chunks by embedding similarity over the vector index."""

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
        limit = max(0, options.limit)
        if not query.strip():
            return SearchResult((), query, 0, 0, 0.0, RetrievalMode.SEMANTIC.value)
        info = self._provider.model_info()
        vector = self._provider.embed_query(query)
        hits = self._vector.search(
            vector, model=info.model, version=info.version, limit=limit
        )
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
        # Apply filters (the vector index has no filter support yet).
        ranked = self._filter(ranked, options)
        for rank, chunk in enumerate(ranked):
            ranked[rank] = dataclasses.replace(chunk, rank=rank)
        return SearchResult(
            chunks=tuple(ranked[:limit]),
            query=query,
            candidate_count=len(ranked),
            returned_count=min(len(ranked), limit),
            duration_ms=(monotonic() - started) * 1000,
            mode=RetrievalMode.SEMANTIC.value,
        )

    def _filter(
        self, chunks: list[RetrievedChunk], options: SearchOptions
    ) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for chunk in chunks:
            if options.roots and chunk.root_id not in options.roots:
                continue
            if options.document_types and chunk.media_type not in options.document_types:
                continue
            if options.path_prefix and not _matches_prefix(
                chunk.relative_path, options.path_prefix
            ):
                continue
            out.append(chunk)
        return out

    def get_document(self, document_id: str) -> DocumentView | None:
        return self._corpus.get_document(document_id)

    def stats(self) -> CorpusStats:
        return self._corpus.stats()

    def status(self) -> IndexStatus:
        return self._corpus.status()


def _matches_prefix(relative_path: str | None, prefix: str) -> bool:
    if not relative_path:
        return False
    prefix = prefix.rstrip("/")
    if not prefix:
        return True
    return relative_path == prefix or relative_path.startswith(prefix + "/")
