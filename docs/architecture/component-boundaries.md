# Component Boundaries

This document defines every logical component, what it owns, what it exposes,
and — critically — what it is **forbidden** from doing. Boundaries are the
anti-drift mechanism: multiple implementers can build against these contracts
without pulling the architecture apart.

---

## 1. Dependency Rule

Dependencies point **downward** only:

```text
Gateway ──▶ Subsystems ──▶ Storage/Corpus
```

- A component may depend on components **below** it.
- It may never depend on components **above** it.
- **No lateral coupling** between peer subsystems (Retrieval ↔ Computation,
  Documents ↔ Tools) except through the gateway or explicitly defined
  interfaces.
- Nothing below the gateway calls the model; nothing below the gateway calls
  Qwen Studio.

Violations to watch for during implementation:

| Anti-pattern | Why it's forbidden |
|--------------|--------------------|
| Retrieval importing reasoning classes | Couples knowledge to workflow |
| A tool calling `generate()` directly | Bypasses policy + permissions |
| MCP layer containing SQL strings | Couples protocol to storage |
| Gateway reading corpus files directly | Bypasses Documents subsystem + immutability |
| Memory manager depending on a specific DB driver | Lock-in to a backend |

---

## 2. Component Contracts

### 2.1 Local Research Gateway (L3)

The single orchestration component. All of the following are **gateway-internal
components**; they are not separate services.

| Component | Owns | Key operations | Must not |
|-----------|------|----------------|----------|
| **Session Manager** | Session lifecycle, continuation, resumption | `open_session`, `close_session`, `resume_session`, `checkpoint` | Decide retrieval or verification policy |
| **Task Router** | Intent classification, complexity assessment | `classify_intent`, `assess_complexity`, `route` | Call the model for reasoning |
| **Reasoning Policy Engine** | Profile registry, profile→policy selection | `select_profile`, `resolve_policy` | Contain provider-specific parameters |
| **Task Decomposer** | Breaking requests into tasks | `decompose`, `plan_dependencies` | Execute tasks |
| **Workflow Engine** | Stage scheduling, skip/repeat, resumption | `run_workflow`, `advance_stage`, `skip`, `repeat` | Talk to storage or the model directly |
| **Context Engine** | Context assembly, budgeting, compaction | `plan_context`, `assemble`, `compact`, `restore` | String-concatenate prompts |
| **Memory Manager** | Fronts all memory stores | `store_claim`, `get_project_context`, `record_decision`, `get_research_state` | Expose raw DB handles |
| **Verification Engine** | Claim/evidence/citation checks | `verify_claim`, `find_contradictions`, `audit_citations` | Modify RAW sources |
| **Artifact Manager** | Artifact creation, versioning, provenance | `create_artifact`, `get_artifact`, `version` | Generate content itself |
| **Inference Adapter** | Profile→policy→provider translation; holds `InferenceProvider`s | `generate`, `stream`, `structured_output`, `tool_call` | Hard-code any provider's parameters |

### 2.2 Subsystems (L4)

| Subsystem | Components | Owns | Must not |
|-----------|-----------|------|----------|
| **Retrieval** | Query Normalizer, Candidate Retriever, Hybrid Ranker, Reranker, Evidence Extractor, Citation Resolver, Context Assembler | Query→context pipeline | Reason about results |
| **Documents** | Discovery, Identification, Hasher, Metadata Extractor, Parser adapters, Normalizer, Chunker, Relationship Extractor | Ingest pipeline | Modify RAW sources |
| **Computation** | Python Sandbox Executor, DuckDB Service | Deterministic compute | Invoke the model |
| **Tools** | Filesystem Tool, Git Tool, other MCP clients | Side-effecting operations behind permissions | Bypass permission checks |

### 2.3 Storage (L5)

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
- Interfaces are **versioned in schemas/** (JSON Schema / type stubs) so the
  MCP layer and storage layer can be implemented independently.
- New capability ⇒ new interface behind the gateway, never a widening of an
  existing god-interface.

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
| New model provider | New `InferenceProvider` implementation |
| New tool | New permission-scoped MCP tool + gateway handler |
| New verification check | New `Verifier` registered in Verification Engine |
| New storage backend | New repository implementation |
| New workflow profile | New `ReasoningProfile` entry (data, not code) |
| New trajectory type | New `Trajectory` implementation (interface-only for now) |

Each is a **closed extension**: you add a conforming implementation, you do not
edit existing orchestration code.
