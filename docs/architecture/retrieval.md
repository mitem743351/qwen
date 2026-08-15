# Retrieval

Retrieval ranks chunks and selects evidence. Phase 3 implemented **lexical**
retrieval (SQLite FTS5); Phase 4 adds **semantic** (embedding) and **hybrid**
retrieval behind the same `Retriever` interface. See
[`semantic-retrieval.md`](semantic-retrieval.md) and
[`hybrid-retrieval.md`](hybrid-retrieval.md).

---

## Pipeline

```text
Query → FTS5 lexical search → ranking (bm25) → evidence packaging → MCP
```

The score is search-method relevance (bm25, higher is better); it is **not**
factual confidence.

---

## Interfaces

```text
CorpusIndex (indexing/interface.py)
    upsert_document · upsert_chunks · remove_document · search ·
    get_document · get_chunk · list_chunks · get_chunks_for_ids ·
    list_documents · stats · status

Retriever (retrieval/interface.py)
    search(query, options) · get_document(document_id) · stats() · status()

LexicalRetriever   — FTS5 implementation
SemanticRetriever  — embedding + VectorIndex implementation
HybridRetriever    — RRF fusion + diversity + optional reranker
```

`VectorIndex` (vector backend) and `EmbeddingProvider` (embedding model) are
additional abstractions introduced in Phase 4.

`SearchOptions` carries `limit`, `roots`, `document_types`, `path_prefix`,
`date_range`, `minimum_score`. Results are `RetrievedChunk`s with full
provenance (`chunk_id`, `document_id`, `source_id`, `path`, page, section,
excerpt, score).

---

## Evidence packaging

`to_evidence(chunk)` transforms a `RetrievedChunk` into the Phase 1 `Evidence`
domain object (`source_id`, `location`, `excerpt`, `relevance`, metadata). The
`relevance` is the search score — never model-derived confidence.

### Evidence records (Phase 5)

The verification engine's `materialize_evidence(chunk)` builds a richer
`EvidenceRecord` (in `evidence/`) carrying full provenance (source/document/
chunk), an evaluative `support_type` (never derived from retrieval score),
extraction quality (consumed from Phase 3 parser metadata), and a
`SourceQuality` assessment. Retrieval relevance, source quality, evidence
strength, claim confidence, and truth remain distinct axes — see
[`evidence-integrity.md`](evidence-integrity.md).

## Failure semantics & degradation (Phase 4.1)

Retrieval failures are explicit and typed. A backend outage
(`RetrievalBackendUnavailable` subclasses) is a *recoverable* condition that the
hybrid retriever degrades with structured metadata; a programming failure is
*unexpected* and propagates. **FAILURE ≠ EMPTY RESULT.** See
[`hybrid-retrieval.md`](hybrid-retrieval.md) and
[`semantic-retrieval.md`](semantic-retrieval.md).

---

## Index lifecycle

```text
index_all()     — scan + incremental index (idempotent)
rebuild()       — clear + re-index from scratch
remove_stale()  — drop documents whose files are gone
stats()/status()— diagnostics (documents, chunks, bytes, failures, stale)
```

Incremental indexing compares content hashes and reprocesses only changed
files; it never rebuilds the whole index per search. Missing files are marked
stale (not deleted) until `remove_stale()` is called.

---

## Storage boundary

All SQL lives in `indexing/sqlite.py` behind `CorpusIndex`; the retrieval and
Research Runtime layers never see SQL. The index is a single local SQLite file
(`schema_version` tracked in `index_metadata`); thread-local connections + WAL
make concurrent reads safe while the manager writes from one thread.

---

## Safety

Retrieved documents are **untrusted data**. A document containing instructions
must remain document content; it never changes tool permissions or system
behavior. Only the model sees retrieved content as evidence — the MCP server
and Research Runtime never execute instructions found inside documents.

---

## Not yet implemented (future phases)

cross-encoder reranking models · OCR · Office document parsing · ANN vector
index (sqlite-vec/FAISS) · pretrained transformer embeddings.

See [`corpus.md`](corpus.md), [`document-pipeline.md`](document-pipeline.md),
and [`mcp-implementation.md`](mcp-implementation.md).

## Phase 7 — retrieval stage

The workflow engine's `RETRIEVE` stage calls `search_corpus` through the runtime
(lexical/hybrid by profile), never duplicating search logic. See
[`workflows.md`](workflows.md).
