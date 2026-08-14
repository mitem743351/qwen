# Retrieval

Retrieval ranks chunks and selects evidence. Phase 3 implements **lexical**
retrieval (SQLite FTS5) only; the interface is the seam where a future
`HybridRetriever` (lexical + semantic + reranking) will attach without changing
the Research Runtime.

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
    get_document · get_chunk · list_documents · stats · status

Retriever (retrieval/interface.py)
    search(query, options) · get_document(document_id) · stats() · status()

LexicalRetriever — FTS5 implementation of Retriever
```

`SearchOptions` carries `limit`, `roots`, `document_types`, `path_prefix`,
`date_range`, `minimum_score`. Results are `RetrievedChunk`s with full
provenance (`chunk_id`, `document_id`, `source_id`, `path`, page, section,
excerpt, score).

---

## Evidence packaging

`to_evidence(chunk)` transforms a `RetrievedChunk` into the Phase 1 `Evidence`
domain object (`source_id`, `location`, `excerpt`, `relevance`, metadata). The
`relevance` is the search score — never model-derived confidence.

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

vector search · embeddings · reranking models · hybrid retrieval · OCR ·
Office document parsing.

See [`corpus.md`](corpus.md), [`document-pipeline.md`](document-pipeline.md),
and [`mcp-implementation.md`](mcp-implementation.md).
