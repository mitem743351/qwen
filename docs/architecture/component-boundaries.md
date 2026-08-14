# Component Boundaries

This document defines every logical component, what it owns, what it exposes,
and — critically — what it is **forbidden** from doing. Boundaries are the
anti-drift mechanism: multiple implementers can build against these contracts
without pulling the architecture apart.

---

## 1. Dependency Rule

Dependencies point **downward** only, across the three runtime layers:

```text
Interface ──▶ MCP Server ──▶ Research Runtime ──▶ Inference Runtime ──▶ Provider
                        └──────────▶ Subsystems ──▶ Storage/Corpus
```

- A component may depend on components **below** it.
- It may never depend on components **above** it.
- **No lateral coupling** between peer subsystems (Retrieval ↔ Computation,
  Documents ↔ Tools) except through the Research Runtime or explicitly defined
  interfaces.
- Nothing below the Research Runtime calls the model; nothing below it calls
  Qwen Studio. (The model backend — the **model plane** — is *outside* the
  system and is only reached by the Inference Runtime, and only in
  `GATEWAY_INFERENCE`/`HYBRID` modes.)
- The Inference Runtime **never** calls upward into the Research Runtime.

**Control-plane reminder.** Runtime ownership is unambiguous because we always
state which plane/runtime a statement refers to:

| Plane | Who controls it | Runtime owner |
|-------|-----------------|----------------|
| Model plane | Qwen Studio (STUDIO_NATIVE) **or** the Inference Runtime (GATEWAY_INFERENCE/HYBRID) | Inference Runtime |
| Agent plane | Research Runtime (orchestration) | Research Runtime |
| Knowledge plane | Research Runtime + Retrieval/Memory/Documents | Research Runtime |
| Interface plane | Qwen Studio / CLI / API / dashboard | MCP Server (adapter) |

Violations to watch for during implementation:

| Anti-pattern | Why it's forbidden |
|--------------|--------------------|
| Retrieval importing reasoning classes | Couples knowledge to workflow |
| A tool calling `generate()` directly | Bypasses the Inference Runtime + permissions |
| MCP layer containing SQL strings | Couples protocol to storage |
| Research Runtime reading corpus files directly | Bypasses Documents subsystem + immutability |
| Memory manager depending on a specific DB driver | Lock-in to a backend |
| Inference Runtime importing workflow classes | Upward dependency; couples provider to policy |
| MCP schema used as internal domain object | Protocol contaminates the domain (ADR 0023) |

---

## 2. Component Contracts

### 2.1 MCP Server

> **Definition.** The **capability exposure boundary** — protocol handling,
> tool registry (MCP view), resource exposure, validation, permissions,
> transport, and translation between MCP schemas and Research Runtime APIs.
> An adapter, not the research system.

| Component | Owns | Key operations | Must not |
|-----------|------|----------------|----------|
| **Transport** | stdio/HTTP/localhost binding | `serve`, `accept` | Encode business logic |
| **Tool Registry (MCP view)** | MCP-facing tool/resource descriptions | `list_tools`, `describe_tool` | Own the internal tool implementation |
| **Schema Adapter** | MCP schema ↔ domain object mapping | `to_domain`, `to_mcp` | Expose domain internals |
| **Permission Boundary** | permission classes + session grants | `authorize` | Grant inference/backend rights |
| **Audit Logger** | request/tool/caller/permission/latency/status | `record` | Log chain-of-thought or secrets |

### 2.2 Research Runtime

> **Definition.** The core application layer (the "operational brain") — usable
> **without MCP** via its own API. Owns everything provider-independent.

```text
Research Runtime
├── task classification + decomposition
├── reasoning profiles + budgets
├── orchestration + workflows
├── context assembly
├── retrieval · memory · evidence
├── verification · artifacts
├── computation coordination
├── state persistence
└── optional delegation to Inference Runtime
```

| Component | Owns | Key operations | Must not |
|-----------|------|----------------|----------|
| **Session Manager** | Session lifecycle, continuation, resumption | `open_session`, `close_session`, `resume_session`, `checkpoint` | Decide retrieval or verification policy |
| **Task Router** | Intent classification, complexity assessment | `classify_intent`, `assess_complexity`, `route` | Call the model for reasoning |
| **Reasoning Policy Engine** | Profile registry, profile→policy selection | `select_profile`, `resolve_policy` | Contain provider-specific parameters |
| **Task Decomposer** | Breaking requests into tasks | `decompose`, `plan_dependencies` | Execute tasks |
| **Workflow Engine** | Stage scheduling, skip/repeat, resumption | `run_workflow`, `advance_stage`, `skip`, `repeat` | Construct provider-specific requests; talk to storage directly |
| **Context Engine** | Context assembly, budgeting, compaction | `plan_context`, `assemble`, `compact`, `restore` | String-concatenate prompts |
| **Memory Manager** | Fronts all memory stores | `store_claim`, `get_project_context`, `record_decision`, `get_research_state` | Expose raw DB handles |
| **Verification Engine** | Claim/evidence/citation checks | `verify_claim`, `find_contradictions`, `audit_citations` | Modify RAW sources |
| **Artifact Manager** | Artifact creation, versioning, provenance | `create_artifact`, `get_artifact`, `version` | Generate content itself |
| **Internal Tool Registry** | Neutral `Tool` abstraction (name, schema, permission, capability) | `register_tool`, `get_tool`, `invoke_tool` | Assume tools are MCP-specific |
| **Mode Selector** | Binds a session/client to a `CapabilityMode` | `resolve_mode`, `assert_capability` | Escalate automatically (hybrid escalation logic is future) |

### 2.3 Inference Runtime

> **Definition.** The provider-facing model execution layer. Owns actual model
> invocation in `GATEWAY_INFERENCE`/`HYBRID`; dormant in `STUDIO_NATIVE`.

| Component | Owns | Key operations | Must not |
|-----------|------|----------------|----------|
| **Provider Router** | provider/model selection | `select_provider`, `select_model` | Make research decisions |
| **Capability Discovery** | `ProviderCapabilities` | `capabilities` | Assume capabilities |
| **Policy Translator** | `InferencePolicy` → provider params (negotiation) | `negotiate`, `translate` | Hard-code any provider's parameters |
| **Invoker** | request construction, streaming, structured output, tool-call handling, retries | `generate`, `stream`, `structured_output`, `tool_call` | Call upward into Research Runtime |
| **Response Normalizer** | normalize provider responses to `InferenceResult` | `normalize` | Persist research state |

### 2.4 Subsystems (L4)

| Subsystem | Components | Owns | Must not |
|-----------|-----------|------|----------|
| **Retrieval** | Query Normalizer, Candidate Retriever, Hybrid Ranker, Reranker, Evidence Extractor, Citation Resolver, Context Assembler | Query→context pipeline | Reason about results |
| **Documents** | Discovery, Identification, Hasher, Metadata Extractor, Parser adapters, Normalizer, Chunker, Relationship Extractor | Ingest pipeline | Modify RAW sources |
| **Computation** | Python Sandbox Executor, DuckDB Service | Deterministic compute | Invoke the model |
| **Tools** | Filesystem Tool, Git Tool, other tool adapters (MCP is one adapter) | Side-effecting operations behind permissions | Bypass permission checks |

### 2.5 Storage (L5)

| Store | Backend (default / larger) | Holds |
|-------|---------------------------|-------|
| Relational system-of-record | SQLite / PostgreSQL | sessions, tasks, claims, evidence, sources, decisions, questions, artifacts metadata |
| Analytical | DuckDB | large tabular data, Parquet/CSV, aggregations |
| Vector index | abstract interface (impl TBD) | embeddings for semantic retrieval |
| Blob store | filesystem | RAW corpus, generated artifacts, caches |

All storage is accessed through **repository interfaces** (`SessionRepository`,
`ClaimRepository`, `SourceRepository`, `ArtifactRepository`, …). The concrete
backend is an implementation detail chosen at configuration time.

---

## 3. Interface Style

Interfaces are defined in `python/` as **protocols / abstract base classes**
(Python's `Protocol` or `abc.ABC`), with Rust exposed as FFI-backed modules
that satisfy the same protocol. Rules:

- Interfaces define **behavior and data shapes**, not backend specifics.
- Every interface has a documented **error model** (what it raises, what it
  retries, what it never does).
- Interfaces are **versioned in schemas/** (`schemas/domain/`, `schemas/mcp/`,
  `schemas/inference/`) so the MCP layer, Research Runtime, Inference Runtime,
  and storage layer can be implemented independently.
- New capability ⇒ new interface behind the Research Runtime, never a widening
  of an existing god-interface.

---

## 4. What Crosses a Boundary

Only three kinds of things cross a boundary:

1. **Commands/requests** (from above, downward).
2. **Results** (from below, upward) — typed, serializable.
3. **Events** (workflow stage transitions, tool completions, verification
   outcomes) — for observability and resumption, never for hidden reasoning.

Raw mutable objects and live DB cursors never cross a boundary.

---

## 5. Extension Points (where growth is expected)

| Extension point | How it's isolated |
|-----------------|-------------------|
| New document type | New `Parser` adapter registered in Documents |
| New corpus folder | Folder name is data; discovery is recursive and config-driven |
| New model provider | New `InferenceProvider` implementation in the Inference Runtime |
| New tool | New entry in the Internal Tool Registry + an MCP/CLI/API adapter decision |
| New verification check | New `Verifier` registered in Verification Engine |
| New storage backend | New repository implementation |
| New workflow profile | New `ReasoningProfile` entry (data, not code) |
| New trajectory type | New `Trajectory` implementation (interface-only for now) |
| New operating mode | New `CapabilityMode` value + capability-matrix row (contract change) |
| New negotiation policy | New outcome handler behind the negotiation layer |

Each is a **closed extension**: you add a conforming implementation, you do not
edit existing orchestration code.
