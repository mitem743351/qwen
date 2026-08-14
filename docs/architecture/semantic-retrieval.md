# Semantic Retrieval

Phase 4 adds semantic (embedding-based) retrieval behind the existing
`Retriever` abstraction. Lexical retrieval remains the stable foundation and is
unchanged.

---

## Embedding backend

- **Provider abstraction:** `EmbeddingProvider` (`model_info()`, `dimension()`,
  `embed_documents()`, `embed_query()`), with `EmbeddingRequest`/`EmbeddingResult`
  and `EmbeddingInfo` (model, version, dimension, distance metric,
  normalization).
- **Default backend:** `HashingEmbeddingProvider` (`hash-ngram-v1`) — a
  deterministic, dependency-free feature-hashing embedder (word tokens + char
  3/4/5-grams hashed into a fixed-dimension L2-normalized vector).

**Decision rationale:** the default must be CPU-only, offline, deterministic,
and must not pull in a large ML framework or require CUDA. The hashing embedder
meets all four; it generalizes over shared morphology/subword structure but
does **not** capture full synonym-level semantics. A pretrained transformer
(e.g. `sentence-transformers` / `fastembed`) is the documented future upgrade
path behind the same `EmbeddingProvider` interface — out of scope for Phase 4.

---

## Vector index

- **Abstraction:** `VectorIndex` (`upsert`, `delete`, `search`, `get`,
  `list_ids`, `stats`, `rebuild`).
- **Default backend:** `SqliteVectorIndex` — vectors stored as JSON in a local
  SQLite table, searched with a deterministic pure-Python cosine scan. `sqlite-vec`
  / FAISS are future upgrades behind the same interface (single-machine,
  dependency-free; no premature optimization).

---

## Embedding versioning & staleness

Every vector record carries `chunk_id`, `model`, `version`, `dimension`, the
vector, and a `text_hash`. The `EmbeddingManager.sync()` embeds only:

- new chunks,
- changed chunks (text hash differs),
- chunks missing an embedding,
- chunks whose model/version changed.

Vectors are searched only within a single `(model, version)`, so vectors from
incompatible models are **never silently mixed**.

---

## Retrieval integration & filter-correct search (Phase 4.1)

`SemanticRetriever` embeds the query, searches the vector index, and joins chunk
metadata back from the corpus index to produce `RetrievedChunk`s with
`semantic_score` set and `lexical_score` absent.

Because the vector backend has no native metadata filtering, the retriever
**overfetches** candidates (`candidate_limit = max(final_k ×
semantic_overfetch_factor, minimum_candidate_pool)`, defaults `5×` and `20`),
applies filters, and only then truncates to the final `limit`. The pipeline is:

```text
query → candidate retrieval (overfetch) → roots → document_types → path_prefix
      → date_range → minimum_score → ranking → diversity → final K
```

`candidate_limit` (how many the vector index is asked for) is distinct from
`final_limit` (`SearchOptions.limit`, what the retriever returns). Overfetch is
a **recall safeguard**, never a confidence measure.

---

## Limitations (honest)

- The hashing embedder is orthographic/subword-level, not a pretrained
  transformer; semantic recall on true synonym paraphrases is limited.
- Brute-force cosine is O(n) in the number of vectors (fine for small/medium
  corpora; a native ANN index is a future upgrade).
- Semantic retrieval never assigns factual confidence — `semantic_score` is a
  similarity, distinct from source quality and claim confidence.

See [`hybrid-retrieval.md`](hybrid-retrieval.md) and
[`setup/semantic-retrieval.md`](../setup/semantic-retrieval.md).
