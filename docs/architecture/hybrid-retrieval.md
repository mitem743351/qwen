# Hybrid Retrieval

`HybridRetriever` combines `LexicalRetriever` and `SemanticRetriever` into a
single ranked evidence stream.

---

## Pipeline

```text
query
  → lexical candidates (FTS5)
  + semantic candidates (vector)
  → candidate fusion (RRF)
  → diversity filtering (max chunks per document)
  → optional reranker
  → ranked evidence
```

---

## Retrieval modes

`RetrievalMode`: `LEXICAL`, `SEMANTIC`, `HYBRID` (default `HYBRID`).

`SearchOptions` carries `mode`, `lexical_k`, `semantic_k`, `final_k`, and
`max_chunks_per_document`; existing filters (`roots`, `document_types`,
`path_prefix`, `minimum_score`) are preserved.

---

## Candidate fusion (deterministic)

**Reciprocal Rank Fusion** with `k = 60`:

```text
rrf(chunk) = Σ 1 / (60 + rank_i)     (rank_i is 1-based within each retriever)
```

Rank-based fusion is used because BM25 (lexical) and cosine (semantic) scores
are not directly comparable. Ties break by `chunk_id` for deterministic
ordering.

---

## Diversity / redundancy control

`max_chunks_per_document` limits how many chunks a single document may
contribute (greedy top-down). No complex novelty algorithm in Phase 4.

---

## Reranker

Optional `Reranker` interface; Phase 4 ships `NoOpReranker` (identity). A
lightweight cross-encoder can be added later without changing search APIs.

---

## Scores (distinct from confidence)

`RetrievedChunk` records `lexical_score`, `semantic_score`, `fusion_score`,
`rerank_score`, and a final `score`; unavailable components are `None` (never
`0`). Retrieval relevance ≠ source quality ≠ claim confidence.

---

## Failure semantics & fallback (Phase 4.1)

Only :class:`~qwen_research.domain.errors.RetrievalBackendUnavailable`
subclasses (`SemanticRetrievalUnavailable`, `VectorIndexUnavailable`,
`EmbeddingBackendUnavailable`, `LexicalRetrievalUnavailable`) trigger fallback.
Unexpected programming failures (TypeError, logic bugs, schema errors) **propagate**
and are never silently converted to zero hits.

| Lexical | Semantic | Result |
|---------|----------|--------|
| available | available | normal hybrid |
| available | unavailable | lexical fallback + `degraded=True`, `degradation_reason="semantic_backend_unavailable"` |
| unavailable | available | semantic-only + `degraded=True`, `degradation_reason="lexical_backend_unavailable"` |
| unavailable | unavailable | raise `RetrievalBackendUnavailable` |

`SearchResult` carries structured degradation metadata: `degraded`,
`degradation_reason` (a stable identifier, not free-form prose),
`semantic_available`, and `lexical_available`.

---

## Evaluation metrics

`SearchResult` records `mode`, `lexical_hits`, `semantic_hits`, and
`intersection_count` for internal evaluation. These are test/diagnostic metrics,
not production quality claims.

See [`semantic-retrieval.md`](semantic-retrieval.md) and
[`retrieval.md`](retrieval.md).
