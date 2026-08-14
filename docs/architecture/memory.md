# Persistent Structured Research Memory

Phase 4 introduces persistent, structured, provenance-bearing memory. Memory is
**categorized**, never a generic key/value dump, and never stores hidden
chain-of-thought.

---

## Categories

| Store | Content | Lifetime |
|-------|---------|----------|
| **Session Memory** | active hypotheses, objective, evidence refs, workflow state | a session |
| **Project Memory** | goals, definitions, scope, important sources, constraints | a project |
| **Research Memory** | claims/conclusions with provenance | durable |
| **Decision Memory** | decision + reason + evidence refs | durable |
| **Question Memory** | unresolved questions (OPEN→…→ANSWERED) | until resolved (history preserved) |
| **Source Memory** | importance, reliability notes, topics, citations, annotations | durable |

---

## Domain objects

`ProjectMemory`, `ResearchMemory`, `DecisionRecord`, `ResearchQuestion`,
`SourceMemory`, `SessionMemoryItem` — strongly typed dataclasses with
`created_at`/`updated_at`/`version`/`status`. `ResearchMemory` carries
`source_refs`/`evidence_refs`/`claim_refs` and a `provenance` map.

---

## Provenance

Research-derived claims **require** evidence references; explicit user/project
metadata is marked `origin = user` and does not. Retrieval scores are never
converted into memory confidence.

### Reference validation (Phase 4.1)

When a `ProvenanceValidator` is configured on the `MemoryService`,
research-derived memory (`origin=RESEARCH`) is validated **before** the write
commits:

- `source_refs` / `evidence_refs` resolve against the corpus (global source and
  chunk ids).
- `claim_refs` resolve against the **same project's** research-memory claim ids
  — a claim from project A never validates in project B.

An unresolved reference raises `ProvenanceError` (identifying the category and
id) and **nothing is persisted** (atomic). Validation lives at the memory
service boundary, so the invariant holds for MCP, CLI, API, and future
workflow writers — not just MCP. User-originated metadata is exempt.

---

## Versioning

Records are versioned (`version` increments on update); answered questions are
never deleted — their history is preserved.

---

## Storage & repositories

SQLite (`SqliteMemoryStore`) with one table per category, physically separate
from the corpus index. Neutral repository interfaces
(`SessionMemoryRepository`, `ProjectMemoryRepository`, `ResearchMemoryRepository`,
`DecisionRepository`, `QuestionRepository`, `SourceMemoryRepository`) keep SQL
out of the Research Runtime.

---

## Retrieval & isolation

`MemoryRetriever.search(project_id, query, memory_type, status, limit)` returns
a ranked, bounded, **project-scoped** set. Project/session isolation is enforced
at repository/query boundaries — never by prompts.

---

## Verification integration (Phase 5)

Phase 5 adds a separate **claims/verification store** (see
[`evidence-integrity.md`](evidence-integrity.md)) that is distinct from memory:
claims and their verification reports live in the verification store, while
`ResearchMemory` remains the provenance-bearing knowledge record. The two are
linked by `claim_refs`: a `ResearchMemory` entry can reference a verified
claim, and the claim's memory-promotion status (`UNREVIEWED → ASSESSED →
SUPPORTED → CORROBORATED`) is updated by the verification engine — but
`UNREVIEWED` claims are never silently promoted. `SUPPORTED ≠ CORROBORATED ≠
TRUE`.

## Context assembly

`build_context()` combines a request with bounded evidence + memory + open
questions into a `ResearchContext` (conservative limits via `ContextBudget`).
All memory/retrieval content is untrusted data; it never carries control-plane
meaning.

---

## MCP surface

```text
get_project_memory    → READ
get_research_memory   → READ
get_open_questions    → READ
save_research_memory  → WRITE   (explicit provenance, no generic blobs)
```

See [`runtime-contracts.md`](runtime-contracts.md) and
[`mcp.md`](mcp.md).
