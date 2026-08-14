# Enabling evidence integrity & verification

Verification is enabled by configuring a **verification database** alongside
the corpus database. It is deterministic and offline — no model, no network,
no GPU.

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `QWEN_RESEARCH_CORPUS_DB` | SQLite corpus index (FTS5) — required for evidence to resolve |
| `QWEN_RESEARCH_CORPUS_ROOT` | allowlisted corpus directory |
| `QWEN_RESEARCH_VERIFICATION_DB` | SQLite verification store (enables the Phase 5 tools) |
| `QWEN_RESEARCH_ENABLE_WRITE` | `"1"` to enable WRITE tools (`create_claim`, `link_claim_evidence`) |

Without `QWEN_RESEARCH_VERIFICATION_DB`, the verification tools are not wired
and the Research Runtime raises `UnsupportedOperationError` for verification
operations. With it, six tools become available:

```text
create_claim            WRITE     create a structured claim (UNREVIEWED)
link_claim_evidence     WRITE     link a claim to corpus evidence
assess_evidence         ANALYZE   assess evidence against a claim
verify_claim            ANALYZE   run the deterministic pipeline → report
get_verification_report READ      read a persisted report by id
get_contradictions      READ      list project contradictions
```

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
        "QWEN_RESEARCH_VERIFICATION_DB": "/path/to/data/verification.db",
        "QWEN_RESEARCH_ENABLE_WRITE": "1"
      }
    }
  }
}
```

---

## Typical flow

```text
create_claim(project_id, text, claim_type=..., source_refs=...)
  → search_corpus(...) to find candidate chunks
  → link_claim_evidence(claim_id, evidence_id, relationship="supports")
  → assess_evidence(claim_id, evidence_id)
  → verify_claim(claim_id)                    # returns VerificationReport
  → get_verification_report(report_id)
  → get_contradictions(project_id)
```

`verify_claim` persists the report and updates the claim's memory-promotion
status. Reports, contradictions, links, and assessments all survive a server
restart (persisted in the verification store).

---

## Persistence

`SqliteVerificationStore` is a single local SQLite database with WAL and
thread-local connections; `schema_version = 1` is recorded in
`verification_meta`. All writes are transactional: a missing claim or evidence
id raises a typed error and persists nothing.

---

## Limitations

- Source-quality and contradiction assessment are **structural/deterministic**;
  there is no semantic or model-assisted judgment in Phase 5.
- `VERIFIED_WITHIN_CORPUS` is scoped to the currently indexed corpus — it is
  not external fact-checking.
- Corroboration independence is a metadata heuristic (document/source/publisher),
  not a claim of editorial independence.

See [`../architecture/evidence-integrity.md`](../architecture/evidence-integrity.md)
and [`../architecture/verification.md`](../architecture/verification.md).
