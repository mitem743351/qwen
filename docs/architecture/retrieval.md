# Retrieval Architecture

Retrieval is a self-contained pipeline, fully separated from reasoning. The
model must never need to understand how the corpus is indexed.

---

## 1. Pipeline

```text
Query
    ↓ Query normalization
    ↓ Candidate retrieval
    │    ├── lexical
    │    ├── semantic
    │    └── metadata
    ↓ Hybrid ranking
    ↓ Reranking
    ↓ Evidence extraction
    ↓ Citation resolution
    ↓ Context assembly
```

| Stage | Responsibility | Output |
|-------|----------------|--------|
| **Query normalization** | Normalize/expand the query (spelling, entity tagging, expansion) | normalized query + facets |
| **Candidate retrieval** | Pull candidates from lexical, semantic, and metadata indexes | candidate set |
| **Hybrid ranking** | Fuse candidate scores (RRF or weighted) | fused ranking |
| **Reranking** | Re-rank top-N with a stronger model | re-ranked list |
| **Evidence extraction** | Extract claim-relevant spans from top documents | evidence records |
| **Citation resolution** | Resolve each evidence span to a source + location | citable references |
| **Context assembly** | Produce a budgeted context package for the Context Engine | assembled context |

Each stage is independently replaceable. Retrieval returns **structured
evidence records** (source id, span, page/chunk, score, citation), never free
text blobs.

---

## 2. Retrieval vs. Reasoning

Retrieval and reasoning are separated by contract:

- Retrieval does **not** decide relevance to an argument — it returns evidence
  ranked by relevance to the *query*.
- The Context Engine (with the workflow) decides *what to put in front of the
  model* and *what priority*.
- The Verification Engine decides *whether evidence supports a claim*.

This three-way split prevents the classic failure where the retriever silently
filters out disconfirming evidence.

---

## 3. Index Architecture

Three coordinated indexes, all derived from the immutable corpus:

| Index | Purpose | Backend |
|-------|---------|---------|
| **Lexical** | Exact/term/phrase search (BM25/FTS) | SQLite FTS5 or Rust indexer (TBD by scale) |
| **Semantic** | Embedding-based similarity | abstract `VectorIndex` interface (impl TBD) |
| **Metadata** | Faceted/filter search (type, author, date, tags, project) | relational store |

**Rule:** the vector database / embedding model are **not** chosen in Phase 0.
They are isolated behind interfaces so the choice can be deferred without
rework. See ADR [0005](decisions/0005-retrieval-pipeline.md).

---

## 4. Corpus Architecture

Source material is **immutable evidence**. Four states:

```text
RAW        — the exact original bytes, content-addressed, never modified
INDEXED    — the parsed/normalized/chunked representation
STRUCTURED — extracted metadata and relationships (entities, citations, structure)
DERIVED    — generated products (summaries, embeddings, analyses) that reference RAW
```

Logical layout (folders are **data**, not code — new folders need no code change):

```text
corpus/
    sources/   papers/   books/   notes/   datasets/   projects/   archive/
```

`archive/` holds deactivated material; it remains indexed or not per
configuration, but RAW is still never deleted.

---

## 5. Document Pipeline

```text
Filesystem discovery → file identification → hashing → metadata extraction
→ document parsing → text normalization → chunking → indexing
→ relationship extraction
```

| Stage | Notes |
|-------|-------|
| Discovery | Recursive, config-driven (Rust candidate for large trees) |
| Identification | MIME/sniff type; route to adapter |
| Hashing | Content address (SHA-256); key for immutability + dedup |
| Metadata extraction | Title, authors, dates, tags, project |
| Parsing | **Adapter per type** — PDF, Markdown, plain text, Office, structured data, source code |
| Normalization | Text cleanup, encoding, whitespace |
| Chunking | Structure-aware where possible (headings, pages) |
| Indexing | Write to lexical/semantic/metadata indexes |
| Relationship extraction | Links, citations, entity co-occurrence |

**New document types are new adapters.** Adding a `.ris` or a `.ipynb` parser
must not touch the rest of the pipeline.

---

## 6. Failure Modes & Mitigations

| Failure mode | Mitigation |
|--------------|------------|
| No lexical match (vocabulary gap) | Hybrid fusion with semantic + metadata fallback |
| Semantic drift returns irrelevant docs | Reranker + evidence-extraction threshold |
| Retriever hides disconfirming evidence | Verification runs counterexample search independently |
| Broken PDF / unparseable file | Adapter reports structured parse error; RAW retained; flagged for review |
| Index drift after corpus change | File watching triggers re-index; index versioned against source hash |
| Metadata-only query | Metadata index answers directly without vector dependency |

---

## 7. Decision Record

- [0005 — Retrieval as a pipeline, separated from reasoning](decisions/0005-retrieval-pipeline.md)
