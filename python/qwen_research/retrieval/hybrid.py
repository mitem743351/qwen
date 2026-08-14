"""Hybrid retrieval: lexical + semantic fusion with deterministic RRF.

Fusion strategy (documented): **Reciprocal Rank Fusion** with ``k = 60``.

    rrf(chunk) = Σ 1 / (60 + rank_i)

summed over each retriever that returned the chunk (rank_i is 1-based within
that retriever's result). Rank-based fusion is used because lexical (BM25) and
semantic (cosine) scores are not directly comparable. Ties break by ``chunk_id``
for deterministic ordering. A document-diversity step then limits the number of
chunks returned per document, and an optional :class:`Reranker` may re-score.
"""

from __future__ import annotations

import dataclasses
from time import monotonic

from qwen_research.retrieval.interface import Retriever
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievalMode,
    RetrievedChunk,
    SearchOptions,
    SearchResult,
)
from qwen_research.retrieval.reranker import NoOpReranker, Reranker

_RRF_K = 60


class HybridRetriever:
    """Combines lexical and semantic retrieval with RRF fusion."""

    def __init__(
        self,
        lexical: Retriever,
        semantic: Retriever,
        *,
        lexical_k: int = 20,
        semantic_k: int = 20,
        final_k: int = 10,
        max_chunks_per_document: int = 3,
        reranker: Reranker | None = None,
    ) -> None:
        self._lexical = lexical
        self._semantic = semantic
        self._lexical_k = max(1, lexical_k)
        self._semantic_k = max(1, semantic_k)
        self._final_k = max(1, final_k)
        self._max_chunks_per_document = max(1, max_chunks_per_document)
        self._reranker = reranker or NoOpReranker()

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        options = options or SearchOptions()
        started = monotonic()

        mode = options.mode
        if mode is RetrievalMode.LEXICAL:
            return self._lexical.search(query, options)
        if mode is RetrievalMode.SEMANTIC:
            return self._semantic.search(query, options)

        # HYBRID
        lexical_k = options.lexical_k or self._lexical_k
        semantic_k = options.semantic_k or self._semantic_k
        final_k = options.final_k or self._final_k
        max_per_doc = options.max_chunks_per_document or self._max_chunks_per_document

        lexical_result = self._safe_search(self._lexical, query, options, lexical_k)
        semantic_result = self._safe_search(self._semantic, query, options, semantic_k)

        lexical_chunks = lexical_result.chunks
        semantic_chunks = semantic_result.chunks

        # Candidate fusion: rank-based RRF over each retriever's ordered list.
        fused: dict[str, tuple[RetrievedChunk, float]] = {}
        for chunk in lexical_chunks:
            fused[chunk.chunk_id] = (chunk, 0.0)
        for chunk in semantic_chunks:
            if chunk.chunk_id not in fused:
                fused[chunk.chunk_id] = (chunk, 0.0)

        def add_rrf(chunks: tuple[RetrievedChunk, ...], weight: float) -> None:
            for i, chunk in enumerate(chunks):
                base, score = fused[chunk.chunk_id]
                score += weight / (_RRF_K + (i + 1))
                fused[chunk.chunk_id] = (base, score)

        add_rrf(lexical_chunks, 1.0)
        add_rrf(semantic_chunks, 1.0)

        ranked = sorted(
            fused.values(),
            key=lambda pair: (-pair[1], pair[0].chunk_id),
        )

        # Attach per-component scores and fusion score.
        lexical_score = {c.chunk_id: c.score for c in lexical_chunks}
        semantic_score = {c.chunk_id: c.score for c in semantic_chunks}
        merged: list[RetrievedChunk] = []
        for chunk, fusion in ranked:
            merged.append(
                dataclasses.replace(
                    chunk,
                    score=fusion,
                    lexical_score=lexical_score.get(chunk.chunk_id),
                    semantic_score=semantic_score.get(chunk.chunk_id),
                    fusion_score=fusion,
                    retrieval_mode=RetrievalMode.HYBRID.value,
                )
            )

        merged = self._diversify(merged, max_per_doc)
        merged = self._reranker.rerank(query, merged)
        for rank, chunk in enumerate(merged):
            merged[rank] = dataclasses.replace(chunk, rank=rank, score=chunk.score)
        merged = merged[:final_k]

        lex_ids = {c.chunk_id for c in lexical_chunks}
        sem_ids = {c.chunk_id for c in semantic_chunks}
        return SearchResult(
            chunks=tuple(merged),
            query=query,
            candidate_count=len(fused),
            returned_count=len(merged),
            duration_ms=(monotonic() - started) * 1000,
            mode=RetrievalMode.HYBRID.value,
            lexical_hits=len(lex_ids),
            semantic_hits=len(sem_ids),
            intersection_count=len(lex_ids & sem_ids),
        )

    def _safe_search(
        self, retriever: Retriever, query: str, options: SearchOptions, k: int
    ) -> SearchResult:
        """Run a sub-retriever, degrading to an empty result on failure.

        A semantic-backend failure must never destroy lexical retrieval; the
        empty result is surfaced in the hybrid metrics (semantic_hits=0).
        """
        try:
            opts = dataclasses.replace(options, limit=k, mode=RetrievalMode.HYBRID)
            return retriever.search(query, opts)
        except Exception:  # noqa: BLE001 — graceful fallback
            return SearchResult((), query, 0, 0, 0.0)

    def _diversify(self, chunks: list[RetrievedChunk], max_per_doc: int) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        seen: dict[str, int] = {}
        for chunk in chunks:
            count = seen.get(chunk.document_id, 0)
            if count >= max_per_doc:
                continue
            seen[chunk.document_id] = count + 1
            out.append(chunk)
        return out

    def get_document(self, document_id: str) -> DocumentView | None:
        return self._lexical.get_document(document_id)

    def stats(self) -> CorpusStats:
        return self._lexical.stats()

    def status(self) -> IndexStatus:
        return self._lexical.status()
