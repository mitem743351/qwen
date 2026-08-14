# Enabling semantic + hybrid retrieval

Semantic retrieval is enabled by configuring a **vector database** alongside the
corpus database. The default embedding backend is deterministic and offline (no
model download, no CUDA).

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_CORPUS_DB` | SQLite corpus index (FTS5) |
| `QWEN_RESEARCH_CORPUS_ROOT` | allowlisted corpus directory |
| `QWEN_RESEARCH_VECTOR_DB` | SQLite vector index (enables semantic/hybrid) |
| `QWEN_RESEARCH_MEMORY_DB` | SQLite memory store (enables memory tools) |
| `QWEN_RESEARCH_ENABLE_WRITE` | `"1"` to enable `save_research_memory` (WRITE) |

Without `QWEN_RESEARCH_VECTOR_DB`, `search_corpus` is lexical-only. With it,
`search_corpus` is **hybrid** by default (`mode: "hybrid"`), and `mode` may be
`lexical`, `semantic`, or `hybrid`.

---

## Example (Qwen Studio MCP config)

```json
{
  "mcpServers": {
    "qwen-research": {
      "command": "python",
      "args": ["-m", "qwen_research.mcp"],
      "cwd": "/path/to/qwen-research-system",
      "env": {
        "QWEN_RESEARCH_CORPUS_DB": "/path/to/data/corpus.db",
        "QWEN_RESEARCH_CORPUS_ROOT": "/path/to/research/papers",
        "QWEN_RESEARCH_VECTOR_DB": "/path/to/data/vectors.db",
        "QWEN_RESEARCH_MEMORY_DB": "/path/to/data/memory.db",
        "QWEN_RESEARCH_ENABLE_WRITE": "1"
      }
    }
  }
}
```

---

## Embedding model lifecycle

- Model: `hash-ngram-v1` (feature-hashing, 256-dim, L2-normalized, cosine).
- Vectors are versioned; changing the model/version causes a re-embed (stale
  vectors are detected, never mixed).
- `EmbeddingManager.sync()` embeds only new/changed chunks (incremental).

## Filter-correct search (overfetch)

Semantic search overfetches candidates (`candidate_limit = final_k ×
semantic_overfetch_factor`, default `5×`, floor `20`), applies metadata filters,
then truncates to the final limit — so a filter cannot silently destroy recall.

## Memory provenance

When a corpus database is configured, `save_research_memory` validates
research-derived `source_refs`/`evidence_refs`/`claim_refs` against the corpus
(and project-scoped claims) before persisting; unresolved references are
rejected (no partial write). User-originated metadata is exempt.

---

## Limitations

- The hashing embedder is subword/orthographic, not a pretrained transformer;
  true synonym-level semantics require a future transformer provider behind the
  same `EmbeddingProvider` interface.
- The vector index is a local brute-force cosine scan (fine for small/medium
  corpora; ANN is a future upgrade).

See [`../architecture/semantic-retrieval.md`](../architecture/semantic-retrieval.md).
