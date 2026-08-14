# Memory Architecture

Persistent memory is **differentiated** by purpose, with an explicit entity
model. There is no generic undifferentiated "memory" store.

---

## 1. The Six Stores

```text
Session Memory        — a single session's working state
Project Memory        — long-lived project scope
Research Memory       — cross-project reusable findings
Knowledge Base        — structured, curated facts and relations
Unresolved Questions  — open items that persist across sessions
Decision History      — auditable record of decisions and rationale
```

| Store | Scope | Lifetime | Typical contents |
|-------|-------|----------|------------------|
| Session Memory | one session | session → checkpoint | active tasks, working hypotheses, stage state |
| Project Memory | one project | project lifetime | project facts, scope, conventions, key sources |
| Research Memory | cross-project | long-lived | reusable findings, methods, conclusions |
| Knowledge Base | global | curated | entities, relations, verified facts |
| Unresolved Questions | cross-session | until resolved | open questions with evidence status |
| Decision History | cross-session | append-only | decisions + rationale + context at time of decision |

The Memory Manager is the **single front door**. No other component touches the
underlying repositories directly.

---

## 2. Entity Model

```text
projects 1─n sessions
projects 1─n documents
sessions 1─n tasks
sessions 1─n decisions
documents 1─n sources (a document may reference many sources)
sources 1─n claims
claims n─m evidence
claims n─m entities
projects 1─n questions
sessions 1─n artifacts
```

Canonical entities:

```text
documents   — an item in the corpus (with a source hash)
sources     — a citable origin (may be external, e.g. a URL, or a corpus doc)
claims      — an assertable statement, possibly attributed
evidence    — a span/source/location that bears on a claim
entities    — named things with relations (knowledge base)
projects    — long-lived scope
sessions    — a research episode
decisions   — append-only record of a decision + rationale
questions   — open or resolved research questions
artifacts   — generated outputs with provenance
```

See [`diagrams/memory-model.md`](diagrams/memory-model.md) for the ER diagram.

---

## 3. What Is and Is Not Stored

**Stored (structured only):**

- hypotheses, claims, evidence references
- decisions and rationale
- unresolved questions
- tool results (inputs/outputs, hashes)
- verification outcomes
- workflow state (completed/current stages)

**Never stored:**

- hidden chain-of-thought
- raw model reasoning traces
- secrets

The persistence layer structurally has **no field** for chain-of-thought. This
is enforced by the schema, not by discipline.

---

## 4. Memory Lifecycle & Compaction

- **Write path:** stage results → Memory Manager → typed repository. Writes are
  idempotent (natural keys by session+task+kind).
- **Read path:** Context Engine requests scoped slices (`get_project_context`,
  `get_research_state`) — the Memory Manager returns *summarized and scoped*
  views, not whole tables.
- **Compaction:** long sessions compact `Session Memory` into summaries that
  are promoted to `Project Memory`/`Research Memory`; the compaction decision
  lives in the Context Engine + Memory Manager, never in the model.
- **Retention:** `Decision History` is append-only. `Unresolved Questions`
  persist until explicitly resolved or superseded.

---

## 5. Storage Backend

- System-of-record: **SQLite** by default, **PostgreSQL** optional (via
  repository interfaces).
- Knowledge base relations: relational tables (entity/relation graph) — no
  dedicated graph DB in v1.
- Analytical slices (e.g. "all claims about X across projects"): **DuckDB**
  reads over exported/attached data.

**Rule:** storage backends are replaceable through repository interfaces; no
business logic knows which backend is in use.

---

## 6. Failure Modes & Mitigations

| Risk | Mitigation |
|------|------------|
| Memory bloat (unbounded growth) | Scoped reads + compaction; budgets per store |
| Stale claims (source updated) | Claims reference source hash + verification status; re-verify on source change |
| Cross-session confusion (wrong project) | Every read scoped by project/session context |
| Decision history polluted | Append-only, structured schema (decision + rationale + context) |
| Backend lock-in | Repository interfaces; SQL dialect isolated |

---

## 7. Decision Record

- [0006 — Differentiated memory stores](decisions/0006-differentiated-memory.md)
