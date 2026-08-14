# MCP Architecture

The MCP layer is the **only** surface the model (via Qwen Studio) can touch.
It is deliberately narrow, semantic, and permission-gated.

---

## 1. Position in the Stack

```text
Qwen Studio (MCP client)
        │  MCP (JSON-RPC)
        ▼
MCP Entrypoint
   ├── Tool registry
   ├── Permission boundary
   ├── Argument validation
   └── Audit logging
        │  typed internal calls
        ▼
Local Research Gateway
```

The MCP Entrypoint is a **translator and gatekeeper**, not an orchestrator. It
contains no reasoning, retrieval, or storage logic.

---

## 2. Tool Surface

A **small number of high-value semantic tools** — never a reflection of every
internal function, and **never** a universal `execute_anything`.

```text
search_corpus           # query the local corpus, return ranked evidence
retrieve_evidence       # fetch evidence for a claim/question with citations
read_source             # read a specific source (permission-gated)
get_research_state      # session/project research state summary
query_database          # run read-only analytical SQL against DuckDB
run_analysis            # run a bounded deterministic analysis (Python/DuckDB)
verify_claim            # verify a claim against evidence/sources
find_contradictions     # detect contradictions across the corpus
save_artifact           # persist a generated artifact with provenance
get_project_context     # retrieve project-scoped memory and context
```

### Design rules for the tool surface

1. **One tool = one semantic verb.** No `do_thing` mega-tools.
2. Each tool declares a **permission class** (see §4).
3. Each tool has a **JSON Schema** for arguments and a typed result schema
   (living in `schemas/`).
4. Tool results are **structured** (typed records), so they flow into context
   and memory without re-parsing.
5. Adding a tool is a **registered addition**, not a change to the gateway's
   orchestration.

---

## 3. Anti-Patterns Explicitly Forbidden

| Forbidden | Why |
|-----------|-----|
| `execute_anything` / arbitrary shell | Violates least privilege; unreviewable |
| Exposing repository internals as tools | Leaks implementation; causes drift |
| A tool that returns raw chain-of-thought | Violates §15 invariant |
| Tool that mutates RAW corpus | Violates immutability |
| Tools with overlapping, ambiguous verbs | Blurs the permission model |

---

## 4. Permission Model

Permissions are **classes**, independently controllable per tool and per
session:

```text
read        — observe (search, read_source, get_* )
analyze     — compute/derive without side effects (query_database, run_analysis, verify_claim)
write       — create new data (save_artifact)
execute     — run code/processes (run_analysis execution, git commands)
destructive — delete/overwrite/mutate existing data
```

Rules:

- `write` and `destructive` are **independently** enabled and default **off**.
- `destructive` additionally requires confirmation by default.
- The permission of a tool call is **declared by the tool**, checked by the
  boundary, and **audited** with the result.
- A denied call returns a structured denial; it is never silently downgraded.

---

## 5. Interaction Flow

```text
MCP request (tool + args)
   → authenticate / identify session
   → resolve tool → validate args against schema
   → check permission class against session grants
   → dispatch to gateway handler
   → record audit event (tool, args-hash, result-hash, latency, permission)
   → return typed result or structured error
```

See [`diagrams/mcp-interaction.md`](diagrams/mcp-interaction.md).

---

## 6. Transport & Runtime Notes

- **Transport:** MCP over stdio or localhost only by default (local-only
  network binding; see [`security.md`](security.md)). No remote exposure in v1.
- **Concurrency:** the entrypoint must handle concurrent tool calls without
  shared mutable state; the gateway serializes state-mutating workflow steps.
- **Rust involvement:** justified only if a high-concurrency MCP server is
  needed (see [`polyglot-boundaries.md`](polyglot-boundaries.md)). For
  single-user local-first, a Python MCP server is acceptable; the decision is
  recorded in ADR [0009](decisions/0009-mcp-semantic-tools.md).

---

## 7. Decision Record

- [0009 — Small semantic MCP surface with class-based permissions](decisions/0009-mcp-semantic-tools.md)
