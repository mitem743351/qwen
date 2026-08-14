# Architecture — Qwen Research System

> **Status:** Phase 0 — Architecture Contract (documentation only)
> **Audience:** Implementers, code agents, reviewers
> **Scope:** This document is the stable, binding architecture contract for the
> "local AI research infrastructure" that extends **Qwen Studio** through MCP.

This phase produces architecture documentation only. No application code, no
database migrations, no servers. Everything in this document is a decision that
later implementation prompts must follow.

---

## 1. Purpose

We are building a **local, single-user-first AI research infrastructure** whose
human-facing interface is **Qwen Studio**. Qwen Studio keeps its native
capabilities (conversation, web search) and is *extended* — never replaced — by
a local runtime that makes the environment behave like a powerful API/agent
runtime.

The system adds, on top of Qwen Studio's conversation surface:

- deep and configurable **reasoning workflows** (FAST → NORMAL → DEEP → XHIGH → EXTREME)
- long-output generation strategies
- iterative reasoning and refinement
- task decomposition, planning, evidence retrieval
- a local private corpus
- persistent research memory and structured knowledge
- contradiction detection, adversarial critique, source verification, citation/provenance
- deterministic computation (Python + DuckDB)
- filesystem, Git, artifact, and workflow execution
- session persistence and task continuation
- optional parallel research trajectories
- future API/inference backends, future local Qwen models, future alternative providers

The architecture must remain useful **even if the Qwen backend changes later**.
That requirement drives every inference-related decision.

---

## 2. Core Architectural Principle

Separate the system into **five conceptual layers** and never couple them
unnecessarily:

```text
Qwen Studio                      (1) Human interface
    ↓
MCP / Gateway                    (2) Protocol boundary
    ↓
Reasoning + Orchestration        (3) Workflow and policy
    ↓
Knowledge / Computation / Tools  (4) Capabilities
    ↓
Local Data                       (5) Storage and corpus
```

A change in any layer must not force a redesign of the others. The contract
between layers is defined by **interfaces and schemas**, not by implementation.

### The Eight Concerns

The system must keep the following concerns distinct at all times. They are
different things and are solved by different mechanisms — **none of them may be
solved by "a longer prompt" alone**:

| # | Concern | Owned by |
|---|---------|----------|
| 1 | Model capability | Inference abstraction (`capability_info`) |
| 2 | Inference configuration | Inference Adapter (`InferencePolicy`) |
| 3 | Reasoning workflow | Workflow Engine + Reasoning Policy Engine |
| 4 | Tool execution | Tools subsystem (behind permissions) |
| 5 | Knowledge retrieval | Retrieval subsystem |
| 6 | Persistent state | Memory Manager + storage layer |
| 7 | Verification | Verification Engine |
| 8 | Deterministic computation | Computation subsystem |

---

## 3. Language Architecture (Polyglot)

| Language | Role | Reserved for |
|----------|------|--------------|
| **Python** | Primary AI/reasoning language | reasoning orchestration, workflow logic, agent logic, retrieval orchestration, document/PDF processing, metadata extraction, embeddings, reranking, verification, inference adapters, evaluation, data science, research workflows, experimental algorithms |
| **Rust** | Systems/performance layer | MCP infrastructure (where justified), high-performance filesystem scanning, indexing, hashing, file watching, high-throughput search, concurrency, process management, OS integration, sandbox infrastructure |
| **TypeScript** | Optional UI infrastructure | monitoring dashboard, session inspection, workflow visualization, corpus/artifact browser, system controls, observability UI. **Not a runtime dependency of the core.** |
| **SQL** | First-class implementation language | SQLite (portable), PostgreSQL (larger), DuckDB (analytical) |
| **Shell** | Ops only | installation, bootstrapping, diagnostics, service startup, backup, migration, deployment. **No business logic in shell.** |

**Binding rules:**

- Prefer **Rust libraries callable from Python via FFI** (e.g. PyO3) over network
  boundaries when a performance or safety advantage is real.
- Avoid unnecessary network boundaries between Python and Rust on a
  single-machine deployment.
- Storage backends are behind **repository interfaces** so SQLite/Postgres are
  replaceable. DuckDB is used for analytical workloads, not as the system of
  record.

See [`docs/architecture/polyglot-boundaries.md`](docs/architecture/polyglot-boundaries.md).

---

## 4. High-Level Components

```text
QWEN STUDIO
    │
    ▼
MCP ENTRYPOINT
    │
    ▼
LOCAL RESEARCH GATEWAY
    │
    ├── Session Manager
    ├── Task Router
    ├── Reasoning Policy Engine
    ├── Task Decomposer
    ├── Workflow Engine
    ├── Context Engine
    ├── Memory Manager
    ├── Verification Engine
    ├── Artifact Manager
    └── Inference Adapter
    │
    ├───────────────┬────────────────┬─────────────────┐
    ▼               ▼                ▼                 ▼
Retrieval       Documents       Computation          Tools
    │               │                │                 │
    ▼               ▼                ▼                 ▼
Search Index    PDF/Office      Python/DuckDB      Filesystem
Metadata        Parsers         Statistics          Git
Memory          Chunking        Simulation          Other MCP
    │
    ▼
LOCAL CORPUS / DATABASES
```

The **Local Research Gateway (LRG)** is the single orchestration component.
Subsystems (Retrieval, Documents, Computation, Tools) are capabilities it
calls — they do not call each other except through explicit interfaces, and
they never call Qwen Studio.

See [`docs/architecture/component-boundaries.md`](docs/architecture/component-boundaries.md).

---

## 5. Reasoning Architecture

Reasoning is an **explicit policy system**. `XHIGH` is **not** a longer system
prompt; it is a *workflow/inference policy*.

```text
ReasoningProfile
    name
    planning_depth
    retrieval_depth
    evidence_threshold
    independent_attempts
    critique_passes
    verification_passes
    context_budget
    output_budget
    continuation_policy
    parallelism
```

Conceptual profiles: `FAST`, `NORMAL`, `DEEP`, `XHIGH`, `EXTREME`.

These names map to **workflow behavior** (how many passes, how much retrieval,
how many critiques) and are translated by the Inference Adapter into whatever
concrete controls the selected Qwen backend actually exposes.

```
ReasoningProfile → InferencePolicy → Provider-specific parameters
```

See [`docs/architecture/reasoning-engine.md`](docs/architecture/reasoning-engine.md) and
[`docs/architecture/inference.md`](docs/architecture/inference.md).

---

## 6. Canonical Deep Workflow

```text
User Request → Intent Classification → Complexity Assessment
→ Reasoning Profile Selection → Task Decomposition → Context Planning
→ Evidence Retrieval → Primary Reasoning → Tool/Computation Execution
→ Counterargument Generation → Critique → Verification → Synthesis
→ Citation/Provenance Audit → Final Response → Persist Research State
```

The Workflow Engine supports **skipping or repeating stages** based on task
complexity. Stages are first-class, individually observable, and resumable.

---

## 7. Iterative Reasoning

```text
Pass 1 → hypothesis
Pass 2 → evidence
Pass 3 → challenge
Pass 4 → correction
Pass 5 → verification
Pass 6 → synthesis
```

**Hidden chain-of-thought is never stored, transmitted, logged, or exposed.**
Only structured reasoning state necessary for continuation, auditing, or
reproducibility is persisted: hypotheses, claims, evidence references,
decisions, unresolved questions, tool results, verification outcomes, workflow
state.

---

## 8. Persistent Memory

Memory is **differentiated**, never a generic "memory" store:

```text
Session Memory        — a single session's working state
Project Memory        — long-lived project scope
Research Memory       — cross-project reusable findings
Knowledge Base        — structured, curated facts and relations
Unresolved Questions  — open items that persist across sessions
Decision History      — auditable record of what was decided and why
```

Related entities: `documents`, `sources`, `claims`, `evidence`, `entities`,
`projects`, `sessions`, `decisions`, `questions`, `artifacts`.

See [`docs/architecture/memory.md`](docs/architecture/memory.md).

---

## 9. Retrieval

Retrieval is a **pipeline**, kept separate from reasoning:

```text
Query → normalization → candidate retrieval (lexical | semantic | metadata)
      → hybrid ranking → reranking → evidence extraction
      → citation resolution → context assembly
```

The model does not need to understand how the corpus is indexed.

See [`docs/architecture/retrieval.md`](docs/architecture/retrieval.md).

---

## 10. Corpus

Source material is **immutable evidence**. States: `RAW`, `INDEXED`,
`STRUCTURED`, `DERIVED`. **RAW is never silently modified.**

```text
corpus/
    sources/  papers/  books/  notes/  datasets/  projects/  archive/
```

Additional folders are supported without code changes (folder names are data,
not code).

---

## 11. Document Pipeline

```text
Filesystem discovery → identification → hashing → metadata extraction
→ parsing → normalization → chunking → indexing → relationship extraction
```

PDF, Markdown, plain text, Office, structured data, and source code are
architecturally independent adapters. New types must not require a pipeline
redesign.

---

## 12. Verification (first-class subsystem)

Claim verification · evidence verification · source quality evaluation ·
contradiction detection · counterexample search · citation auditing ·
calculation validation · cross-document consistency.

Callable **automatically** (deep workflows) **and explicitly** (MCP).

---

## 13. Computation

Probabilistic/model reasoning is separated from deterministic computation.

- **Python**: statistics, numerical analysis, simulations, ML, scientific workflows.
- **DuckDB**: analytical SQL over large tabular data (Parquet/CSV), aggregations, filtering, joins.

The model **requests** computations and **interprets** outputs; it never
manually performs large numerical operations.

---

## 14. MCP

MCP exposes a **small number of high-value semantic tools** — never every
internal function, and **never** a universal `execute_anything`.

```text
search_corpus · retrieve_evidence · read_source · get_research_state
query_database · run_analysis · verify_claim · find_contradictions
save_artifact · get_project_context
```

Permissions distinguish `read`, `analyze`, `write`, `execute`, `destructive`.
`write` and `destructive` are independently controllable.

See [`docs/architecture/mcp.md`](docs/architecture/mcp.md).

---

## 15. Context

A dedicated **Context Engine** decides what enters model context, what stays
out, what is summarized vs. verbatim, what is deduplicated, how evidence is
prioritized, how budget is allocated across task components, and how long
sessions are compacted and restored. Context management is **never** simple
string concatenation.

---

## 16. Long Output

Long outputs are a **workflow capability**: single response, sectioned
generation, continuation, artifact-first generation, incremental synthesis,
final assembly.

State maintained: `completed_sections`, `remaining_sections`, `claims_used`,
`citations_used`, `style_constraints`, `open_issues`. Large reports must exceed
a single response limit without losing coherence.

---

## 17. Parallel Reasoning (future-proofed)

Interfaces are established now; distributed agents are **not** implemented yet.

```text
Trajectory A → supporting evidence
Trajectory B → opposing evidence
Trajectory C → methodological critique
Trajectory D → local corpus
Trajectory E → current web evidence
```

Trajectories are independently evaluated before final synthesis.

---

## 18. Inference Abstraction

Provider-independent interface:

```text
InferenceProvider
    generate()
    stream()
    structured_output()
    tool_call()
    model_info()
    capability_info()
```

Adapters: Qwen API, Qwen-compatible endpoint, future local Qwen, future
alternative providers. Qwen API parameters are **not** hard-coded into the
reasoning engine; a translation layer maps `ReasoningProfile → InferencePolicy
→ provider-specific parameters`.

See [`docs/architecture/inference.md`](docs/architecture/inference.md).

---

## 19. Artifacts

Generated outputs are first-class objects:

```text
artifact_id · type · path · created_at · source_session · source_task
source_claims · source_documents · generation_metadata · version
```

Artifacts are reproducible and traceable.

---

## 20. Security

Assume the model makes mistakes. Enforce least privilege, filesystem
allowlists, tool permissions, execution sandboxing, local-only network binding
by default, secret isolation, audit logging, and destructive-operation
confirmation. The model never has unrestricted host access by default.

See [`SECURITY.md`](SECURITY.md) and [`docs/architecture/security.md`](docs/architecture/security.md).

---

## 21. Observability

Hooks for: structured logs, tool execution logs, workflow state, latency, token
usage (where available), retrieval statistics, verification results, errors,
audit events. **Hidden chain-of-thought is never logged.**

---

## 22. Repository Structure (baseline)

```text
qwen-research-system/
├── apps/            gateway/ · worker/ · dashboard/
├── python/          reasoning/ · orchestration/ · retrieval/ · context/
│                    memory/ · documents/ · verification/ · inference/
│                    computation/ · workflows/
├── rust/            core/ · mcp/ · filesystem/ · indexer/ · search/ · process/
├── typescript/      dashboard/
├── data/            database/ · index/ · memory/ · cache/ · sessions/
├── corpus/          sources/ · papers/ · books/ · notes/ · datasets/
│                    projects/ · archive/
├── workflows/  prompts/  schemas/  config/  tests/  scripts/  docs/
├── ARCHITECTURE.md  SECURITY.md  README.md  pyproject.toml  .env.example
```

This is a **logical structure**, not an instruction to create every directory now.

---

## 23. Architectural Constraints (binding)

1. Single-user, local-first deployment must remain fully supported.
2. No unnecessary microservices.
3. Prefer local IPC, libraries, or FFI over network calls between components on one machine.
4. Python is the primary AI language.
5. Rust only where performance, concurrency, filesystem, or system control justifies it.
6. TypeScript remains optional.
7. All model providers go through the inference abstraction.
8. All tool access passes through permission boundaries.
9. Raw research sources are immutable.
10. Deterministic computation is separated from model reasoning.
11. Retrieval is separated from reasoning.
12. Verification is independently callable.
13. Long-running research is resumable.
14. Every important derived artifact has provenance.
15. Hidden chain-of-thought is never stored, transmitted, or exposed.
16. Do not optimize prematurely; identify extension points without building unneeded infrastructure.

---

## Document Index

| Document | Covers |
|----------|--------|
| [system-overview](docs/architecture/system-overview.md) | End-to-end picture, layer responsibilities |
| [component-boundaries](docs/architecture/component-boundaries.md) | Interfaces, ownership, dependency rules |
| [polyglot-boundaries](docs/architecture/polyglot-boundaries.md) | Language responsibilities, FFI policy |
| [data-flow](docs/architecture/data-flow.md) | Request → response, persistence, state transitions |
| [reasoning-engine](docs/architecture/reasoning-engine.md) | Profiles, workflow engine, iterative passes |
| [mcp](docs/architecture/mcp.md) | Tool surface, permissions, protocol |
| [retrieval](docs/architecture/retrieval.md) | Pipeline, ranking, corpus, document pipeline |
| [memory](docs/architecture/memory.md) | Stores, entity model, lifecycle |
| [inference](docs/architecture/inference.md) | Provider abstraction, policy translation |
| [security](docs/architecture/security.md) | Threat model, boundaries, sandboxing |
| [architecture-review](docs/architecture/architecture-review.md) | Risks, failure modes, Rust-value analysis |
| [implementation-phases](docs/architecture/implementation-phases.md) | Phase 0–11 roadmap |
| [decisions/](docs/architecture/decisions/) | ADRs for major architectural decisions |
| [diagrams/](docs/architecture/diagrams/) | Mermaid diagrams |
