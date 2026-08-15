# MCP Architecture

The MCP layer is the **only** surface the model (via Qwen Studio) can touch.
It is deliberately narrow, semantic, and permission-gated.

> **Implemented.** The MCP foundation (Phase 2) is implemented in
> `python/qwen_research/mcp/` (stdio transport, Research-Runtime tools,
> permissions, error normalization). Phase 3 adds retrieval tools
> (`search_corpus`, `get_source`); Phase 4 adds hybrid search and the memory
> tools; Phase 5 adds the evidence-integrity tools (`create_claim`,
> `link_claim_evidence`, `assess_evidence`, `verify_claim`,
> `get_verification_report`, `get_contradictions`); Phase 6 adds the
> computation tools (`describe_dataset`, `run_query`, `run_analysis`,
> `get_computation_result`, `run_python`). See
> [`mcp-implementation.md`](mcp-implementation.md) for what exists vs. future
> capability.

> ### MCP ≠ Inference Control
>
> MCP extends a model with **capabilities**; it does **not** grant the MCP
> server control over the host client's model inference parameters, reasoning
> budget, hidden thinking, max generation tokens, temperature, or `top_p`.
> Providing tools is **Tool Control**, which is distinct from **Inference
> Control**. The MCP layer makes no claim about the host model's inference
> loop, and must never be documented as if it could.

---

## 1. Position in the Stack

```text
Qwen Studio (MCP client)
        │  MCP (JSON-RPC)
        ▼
MCP Server
   ├── Tool registry (MCP view)
   ├── Permission boundary
   ├── Argument validation
   ├── Schema adapter (MCP ↔ domain)
   └── Audit logging
        │  typed internal calls
        ▼
Research Runtime
```

The MCP Server is a **translator and gatekeeper** — an adapter onto the
Research Runtime — not an orchestrator and not the research system. It
contains no reasoning, retrieval, or storage logic.

---

## 2. Tool Surface

A **small number of high-value semantic tools** — never a reflection of every
internal function, and **never** a universal `execute_anything`.

```text
search_corpus           # query the local corpus (lexical/semantic/hybrid) ✅ (Phases 3–4)
get_source              # document metadata + structure for a source id   ✅ (Phase 3)
get_project_memory      # project-scoped memory                           ✅ (Phase 4)
get_research_memory     # research-derived claims with provenance         ✅ (Phase 4)
get_open_questions      # unresolved research questions                   ✅ (Phase 4)
save_research_memory    # save research memory (WRITE)                    ✅ (Phase 4)
create_claim            # create a structured claim (UNREVIEWED)          ✅ (Phase 5, WRITE)
link_claim_evidence     # link a claim to evidence with a relationship    ✅ (Phase 5, WRITE)
assess_evidence         # assess evidence against a claim                 ✅ (Phase 5, ANALYZE)
verify_claim            # run deterministic verification → report         ✅ (Phase 5, ANALYZE)
get_verification_report # read a persisted verification report            ✅ (Phase 5, READ)
get_contradictions      # list project contradictions                     ✅ (Phase 5, READ)
describe_dataset        # profile a dataset (schema/statistics/preview)   ✅ (Phase 6, READ)
run_query               # validated, parameterized SQL over datasets      ✅ (Phase 6, ANALYZE)
run_analysis            # structured analysis (statistics/group/…/simulate) ✅ (Phase 6, ANALYZE)
get_computation_result  # read a persisted computation result by id       ✅ (Phase 6, READ)
run_python              # sandboxed Python (disabled by default)          ✅ (Phase 6, EXECUTE)
plan_research           # classify + plan a task deterministically        ✅ (Phase 7, ANALYZE)
start_research          # create + execute a research workflow run        ✅ (Phase 7, ANALYZE)
get_research_status     # run status/progress/degradation                 ✅ (Phase 7, READ)
pause_research          # pause a run                                      ✅ (Phase 7, ANALYZE)
resume_research         # resume a paused run                              ✅ (Phase 7, ANALYZE)
cancel_research         # cancel a run                                     ✅ (Phase 7, ANALYZE)
get_research_summary    # bounded research summary                         ✅ (Phase 7, READ)
retrieve_evidence       # fetch evidence for a claim/question with citations (future)
read_source             # read a specific source (permission-gated)      (future)
get_research_state      # session/project research state summary          ✅ (Phase 2)
query_database          # run read-only analytical SQL against DuckDB     (future — superseded by run_query)
find_contradictions     # detect contradictions across the corpus         (future)
save_artifact           # persist a generated artifact with provenance    (future)
get_project_context     # retrieve project-scoped memory and context      (future)
```

### Design rules for the tool surface

1. **One tool = one semantic verb.** No `do_thing` mega-tools.
2. Each tool declares a **permission class** (see §4).
3. Each tool has a **JSON Schema** for arguments and a typed result schema
   (living in `schemas/mcp/`).
4. Tool results are **structured** (typed records), so they flow into context
   and memory without re-parsing.
5. Adding a tool is a **registered addition** to the Internal Tool Registry
   plus a deliberate MCP-exposure decision — not a change to the Research
   Runtime's orchestration.
6. **MCP is not the internal plugin architecture.** Internal tools exist
   independently of MCP; MCP is one adapter that publishes a curated subset
   (see [`runtime-boundaries.md`](runtime-boundaries.md)).

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

> **Two separate boundaries.** MCP tool permissions and inference ownership are
> **distinct** security boundaries. A client granted MCP `read`/`analyze`
> access does **not** thereby gain permission to invoke arbitrary model
> backends; that requires `GATEWAY_INFERENCE`/`HYBRID` to be configured and the
> relevant credentials scoped to the Inference Runtime (see
> [`security.md`](security.md#inference-ownership-as-a-boundary)).

Permissions are **classes**, independently controllable per tool and per
session:

```text
read        — observe (search, get_source, get_*_memory, get_open_questions, get_verification_report, get_contradictions, describe_dataset, get_computation_result, get_research_status, get_research_summary)
analyze     — compute/derive without side effects (create_session, execute_task, run_query, run_analysis, verify_claim, assess_evidence, plan_research, start_research, pause_research, resume_research, cancel_research)
write       — create new data (save_research_memory, save_artifact, create_claim, link_claim_evidence)
execute     — run code/processes (run_python)
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
   → resolve tool → validate args against MCP schema
   → adapt to domain object (MCPRequest)
   → check permission class against session grants
   → dispatch to Research Runtime handler
   → adapt result to MCPResult
   → record audit event (tool, args-hash, result-hash, latency, permission)
   → return typed result or structured error
```

See [`diagrams/mcp-interaction.md`](diagrams/mcp-interaction.md).

---

## 6. Transport & Runtime Notes

- **Transport:** MCP over stdio or localhost only by default (local-only
  network binding; see [`security.md`](security.md)). No remote exposure in v1.
- **Concurrency:** the MCP Server must handle concurrent tool calls without
  shared mutable state; the Research Runtime serializes state-mutating workflow
  steps.
- **Rust involvement:** justified only if a high-concurrency MCP server is
  needed (see [`polyglot-boundaries.md`](polyglot-boundaries.md)). For
  single-user local-first, a Python MCP server is acceptable; the decision is
  recorded in ADR [0009](decisions/0009-mcp-semantic-tools.md).

---

## 7. Decision Record

- [0009 — Small semantic MCP surface with class-based permissions](decisions/0009-mcp-semantic-tools.md)
