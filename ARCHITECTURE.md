# Architecture — Qwen Research System

> **Status:** Phase 9.3 — Tool-execution persistence & idempotency.
> The architecture (Phases 0, 0.5, 0.75) is the stable baseline; Phases 1–1.2
> established and hardened the core contracts; Phases 2–3 added the MCP server
> and lexical corpus retrieval; Phase 4 adds semantic + hybrid retrieval and
> persistent structured memory; Phase 5 adds the deterministic evidence-integrity
> and verification foundation; Phase 6 adds the deterministic computation layer;
> Phase 7 adds the deterministic orchestration layer; Phase 8 connects the
> Research Runtime to real model providers (beginning with Qwen) through a
> strict provider-neutral inference boundary; Phase 8.1 makes Qwen capability
> discovery model-specific and current (2026); Phase 8.2 completes per-model
> capability coverage; Phase 8.3 makes Qwen model availability and effective
> capability resolution contextual (model + endpoint + region + plan +
> inference mode); Phase 8.4 makes the endpoint profile drive the network
> endpoint and adds transient reasoning state for multi-turn continuation;
> Phase 9 adds the controlled model ↔ tool-call loop and the hybrid
> Studio/Gateway boundary contract.
> **Audience:** Implementers, code agents, reviewers
> **Scope:** This document is the stable, binding architecture contract for the
> "local AI research infrastructure" that extends **Qwen Studio** through MCP.

This phase produces architecture documentation only. No application code, no
database migrations, no servers. Everything in this document is a decision that
later implementation prompts must follow.

> ### Foundational statement (binding)
>
> **Qwen Studio can be enhanced by local MCP capabilities without giving the
> local system direct control of Studio's inference. Direct XHIGH-style
> inference control exists only where the active inference backend exposes that
> control. Gateway-owned and hybrid modes provide the architectural path to
> true API-grade orchestration.**

> ### Runtime statement (binding, Phase 0.75)
>
> **MCP is an external capability boundary. The Research Runtime is the
> provider-independent research and orchestration layer. The Inference Runtime
> is the provider-facing model execution layer. They are logically separate
> even when deployed in one local process.**

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
MCP Server                       (2) Capability exposure boundary
    ↓
Research Runtime                 (3) Workflow, policy, orchestration
    ↓
Knowledge / Computation / Tools  (4) Capabilities
    ↓
Local Data                       (5) Storage and corpus
```

A change in any layer must not force a redesign of the others. The contract
between layers is defined by **interfaces and schemas**, not by implementation.

### The Three Runtime Layers

The former monolithic "gateway" is replaced by **three logically distinct
runtime layers** (see
[`docs/architecture/runtime-boundaries.md`](docs/architecture/runtime-boundaries.md)):

| Runtime | Role | Never owns |
|---------|------|------------|
| **MCP Server** | capability exposure: protocol, tool registry (MCP view), validation, permissions, transport | research logic, reasoning policy, retrieval, memory, workflows |
| **Research Runtime** | core application: classification, decomposition, profiles/budgets, orchestration, workflows, context, retrieval, memory, verification, artifacts, state | provider-specific inference orchestration |
| **Inference Runtime** | model invocation: provider/model selection, capability discovery, policy translation, request construction, streaming, retries, response normalization | research memory, indexing, retrieval, workflow policy, verification, provenance |

These are **logical boundaries first** — in-process modules on a single
machine, not three mandatory network daemons.

### Inference Ownership Rule

> **MCP extends a model with capabilities; it does not inherently grant the MCP
> server control over the host client's model inference parameters or reasoning
> loop.**

```text
Tool Control        ≠   Inference Control
Workflow Influence  ≠   Direct Model-Inference Control
```

The system must never claim a capability the selected interface does not
expose. There are **three operating modes** (see
[`docs/architecture/operating-modes.md`](docs/architecture/operating-modes.md)):

| Mode | Inference owner | What the local system provides |
|------|-----------------|-------------------------------|
| `STUDIO_NATIVE` | Qwen Studio | MCP tools, corpus, retrieval, memory, computation, verification, artifacts |
| `GATEWAY_INFERENCE` | Research Runtime + Inference Runtime | All of the above **plus** direct workflow/inference orchestration via `InferenceProvider` |
| `HYBRID` | Both (escalation boundary) | Studio-native for normal tasks; Research-Runtime-owned for escalated deep tasks |

### The Four Control Planes

To avoid ambiguity in the word "gateway", the system is described in four
**control planes**, now mapped to runtime ownership:

| Plane | Owns | Examples | Runtime owner |
|-------|------|----------|---------------|
| **Model plane** | The actual inference backend | model, reasoning, generation, context window, provider parameters | Inference Runtime (+ Model Provider) |
| **Agent plane** | The orchestration system | planning, tool selection, workflow, iteration, parallelism, retry, continuation | Research Runtime |
| **Knowledge plane** | The persistent research infrastructure | documents, retrieval, memory, claims, evidence, datasets | Research Runtime + Retrieval/Memory/Documents |
| **Interface plane** | The user-facing interaction | Qwen Studio, CLI, API, dashboard, future clients | MCP Server (adapters) |

### The Eight Concerns

The system must keep the following concerns distinct at all times. They are
different things and are solved by different mechanisms — **none of them may be
solved by "a longer prompt" alone**:

| # | Concern | Owned by |
|---|---------|----------|
| 1 | Model capability | Inference Runtime (`capabilities()`) |
| 2 | Inference configuration | Inference Runtime (`InferencePolicy`) |
| 3 | Reasoning workflow | Research Runtime (Workflow Engine + Reasoning Policy Engine) |
| 4 | Tool execution | Research Runtime (Tools subsystem, behind permissions) |
| 5 | Knowledge retrieval | Research Runtime (Retrieval subsystem) |
| 6 | Persistent state | Research Runtime (Memory Manager + storage layer) |
| 7 | Verification | Research Runtime (Verification Engine) |
| 8 | Deterministic computation | Research Runtime (Computation subsystem) |

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
QWEN STUDIO  /  FUTURE CLI / API / DASHBOARD
    │
    ▼
MCP SERVER   (capability exposure: protocol · tools · permissions · transport)
    │
    ▼
RESEARCH RUNTIME   (the operational brain)
    ├── Session Manager
    ├── Task Router
    ├── Reasoning Policy Engine
    ├── Task Decomposer
    ├── Workflow Engine
    ├── Context Engine
    ├── Memory Manager
    ├── Verification Engine
    ├── Artifact Manager
    └── Internal Tool Registry
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

    │
    ▼ (GATEWAY_INFERENCE / HYBRID only)
INFERENCE RUNTIME   (provider routing · capability discovery · policy translation)
    │
    ▼
INFERENCE PROVIDER  (Qwen API / local Qwen / other)
```

The **Research Runtime** is the core orchestration component (the "operational
brain"). Subsystems (Retrieval, Documents, Computation, Tools) are capabilities
it calls — they do not call each other except through explicit interfaces, and
they never call Qwen Studio. The **Inference Runtime** sits below it and owns
model invocation; it is only exercised in `GATEWAY_INFERENCE`/`HYBRID` modes.

> **Inference ownership is conditional.** In `STUDIO_NATIVE` mode the Inference
> Runtime is not on the request path — Qwen Studio owns inference and merely
> calls MCP tools backed by the Research Runtime's capabilities.

See [`docs/architecture/component-boundaries.md`](docs/architecture/component-boundaries.md),
[`docs/architecture/runtime-boundaries.md`](docs/architecture/runtime-boundaries.md), and
[`docs/architecture/operating-modes.md`](docs/architecture/operating-modes.md).

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

> A `ReasoningProfile` is an abstract **resource-allocation and workflow
> policy**. It does **not** guarantee a specific model reasoning budget unless
> the active inference owner/provider exposes the required controls. Each
> profile implies a [`ReasoningBudget`](docs/architecture/capability-negotiation.md#2-reasoningbudget)
> (`inference_budget`, `retrieval_budget`, `tool_budget`, `context_budget`,
> `verification_budget`, `output_budget`, `time_budget`, `parallelism_budget`).

These names map to **workflow behavior** (how many passes, how much retrieval,
how many critiques) and are translated by the Inference Runtime into whatever
concrete controls the selected Qwen backend actually exposes — through an
explicit **capability negotiation** step.

```
ReasoningProfile → InferencePolicy → Capability negotiation → Provider-specific parameters
```

In `STUDIO_NATIVE` mode, `XHIGH`/`EXTREME` translate primarily into richer tool
usage, better retrieval, stronger evidence, and verification tools — **not**
direct control over hidden model thinking tokens. In `GATEWAY_INFERENCE` mode
they may additionally control provider-specific inference parameters where
supported.

See [`docs/architecture/reasoning-engine.md`](docs/architecture/reasoning-engine.md),
[`docs/architecture/inference.md`](docs/architecture/inference.md), and
[`docs/architecture/capability-negotiation.md`](docs/architecture/capability-negotiation.md).

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

> **Phase 7 (implemented).** The deterministic orchestration layer is live:
> `ResearchTask` classification, `ResearchPlan`/`WorkflowRun` persistence, a
> `WorkflowEngine` with registered stage executors (retrieve → assess → verify
> → compute → memory → synthesize → finalize), bounded evidence-gap /
> contradiction / computation loops, explicit retry policies, idempotent
> re-entry, resource accounting, and a provider-neutral `SynthesisRequest`
> boundary for the future inference runtime. See
> [`docs/architecture/orchestration.md`](docs/architecture/orchestration.md).

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

> **Phase 5 foundation (implemented).** The deterministic baseline is live:
> structured claims (`claims/`), evidence records (`evidence/`), source-quality
> assessment (`sources/`), contradiction analysis (`contradictions/`), and a
> scoped verification engine (`verification/`) that emits `VerificationReport`s
> and coverage metrics. Verification statuses are **bounded** —
> `VERIFIED_WITHIN_CORPUS` means "passed the configured deterministic
> procedures against the currently indexed corpus", never absolute truth. See
> [`docs/architecture/evidence-integrity.md`](docs/architecture/evidence-integrity.md).

---

## 13. Computation

Probabilistic/model reasoning is separated from deterministic computation.

- **Python**: statistics, numerical analysis, simulations, ML, scientific workflows.
- **DuckDB**: analytical SQL over large tabular data (Parquet/CSV), aggregations, filtering, joins.

The model **requests** computations and **interprets** outputs; it never
manually performs large numerical operations.

> **Phase 6 foundation (implemented).** The deterministic baseline is live:
> `ComputationRequest`/`ComputationResult` domain objects, a `ComputationEngine`
> with an execution registry, a DuckDB backend behind an `AnalyticsEngine`
> boundary (external access disabled, SQL validated and parameterized), a
> controlled Python subprocess sandbox, seeded simulation, bounded execution
> profiles, structured results with full provenance (query/code hashes, dataset
> freshness), artifact storage, and MCP tools (`describe_dataset`, `run_query`,
> `run_analysis`, `get_computation_result`, `run_python`). See
> [`docs/architecture/computation.md`](docs/architecture/computation.md).

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

> **MCP ≠ inference control.** MCP exposes *capabilities*; it does not grant
> the local system control over the host client's inference parameters,
> reasoning budget, or generation limits. Tool permissions and inference
> ownership are **separate** security boundaries. The MCP Server is an adapter
> onto the Research Runtime, not the research system itself.

See [`docs/architecture/mcp.md`](docs/architecture/mcp.md) and
[`docs/architecture/operating-modes.md`](docs/architecture/operating-modes.md).

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
    capabilities()        # ProviderCapabilities — what this backend can do
    model_info()
    generate()
    stream()
    structured_output()
    tool_call()
```

Adapters: Qwen API, Qwen-compatible endpoint, future local Qwen, future
alternative providers. Qwen API parameters are **not** hard-coded into the
reasoning engine; a translation layer maps `ReasoningProfile → InferencePolicy
→ capability negotiation → provider-specific parameters`. Unsupported
parameters are handled explicitly (`APPLY` / `DEGRADE` / `EMULATE` / `REJECT`),
never silently assumed.

See [`docs/architecture/inference.md`](docs/architecture/inference.md) and
[`docs/architecture/capability-negotiation.md`](docs/architecture/capability-negotiation.md).

> **Phase 8 (implemented).** The provider-neutral `InferenceRuntime` and the
> `QwenProvider` adapter are live: capability discovery, negotiation, request
> mapping, response normalization, streaming, structured output, tool-call
> representation, retries, timeouts, and usage accounting — with credentials
> isolated from the domain model and hidden reasoning never persisted. The
> single-invocation `GATEWAY_INFERENCE` flow works end-to-end. See
> [`docs/architecture/inference-runtime.md`](docs/architecture/inference-runtime.md).
>
> **Phase 8.1 (implemented).** Capability discovery is now **model-specific**
> (a `qwen_models.py` catalog drives per-model context windows, thinking mode,
> and numeric `thinking_budget`); full tool schemas are represented (execution
> remains Phase 9); structured output is validated against the requested JSON
> Schema; streaming enforces a real `stream_idle_seconds` idle timeout; and the
> Qwen API documentation reflects the current 2026 contract.
>
> **Phase 8.2 (implemented).** The catalog now also carries per-model
> `preserve_thinking`, `structured_output`, `tool_calling`, and `streaming`
> facts; `preserve_thinking` is emitted only on the models that support it
> (`qwen3.7-max`/`qwen3.7-plus`); thinking-only `qwq-*` models are marked
> without structured output/tool calling; the unverified `qwen3.8-max` entry was
> removed; and `qwen3.7-max` is pinned against official docs (1M context,
> 65,536 max output) with a documented catalog-maintenance process.
>
> **Phase 8.3 (implemented).** Model availability is now **contextual**
> (model + endpoint + region + plan + inference mode) via `qwen_availability.py`
> (`QwenEndpointProfile`, `QwenModelAvailabilityResolver`, `ModelDiagnostic`);
> `qwen3.8-max-preview` is represented as an official PREVIEW / Token-Plan-only
> model (not removed, not fabricated); effective capabilities gate
> mode-dependent flags (structured output off while thinking is on); function
> calling and built-in tools are kept separate (built-in tools cataloged, never
> invoked); and distinct availability errors replace a blanket
> `ModelNotFoundError`.
>
> **Phase 8.4 (implemented).** The endpoint profile now **controls** the HTTP
> endpoint (`base_url` is authoritative; a conflicting `api_endpoint` raises);
> `Message.reasoning_content` carries transient hidden reasoning for
> `preserve_thinking` multi-turn continuation (marked `transient`, never
> serialized/persisted); `qwen3.8-max-preview` context corrected to 983,616; a
> guard raises instead of silently dropping required reasoning state; and
> `reasoning_effort` is explicitly cataloged-but-not-executed (Phase 10).
>
> **Phase 9 (implemented).** The controlled tool-call loop
> (`research/tool_loop.py`) lets Qwen request tools that the Research Runtime
> authorizes and executes through the internal registry, then continues the
> same inference session with normalized tool results. The model never owns the
> capability boundary: permissions, project/session scope, loop budgets,
> repeated-call guards, and tool-result limits are all runtime-enforced. The
> hybrid Studio/Gateway boundary contract (`research/hybrid.py`) is defined but
> automatic escalation is not implemented.
>
> **Phase 9.1 (implemented).** The loop continues after tool execution and
> emits `LOOP_LIMIT` only on an actual limit; malformed Qwen tool arguments are
> flagged (`ToolCall.arguments_error`) and rejected as `INVALID_ARGUMENTS`
> rather than silently normalized to `{}`.
>
> **Phase 9.2 (implemented).** Every tool call is validated immediately before
> its own execution, and each call receives exactly one outcome — a partial
> batch produces explicit `RESOURCE_LIMIT` / `CANCELLED` results for the
> unexecuted remainder, so no assistant `tool_calls` message enters a
> continuation with a dangling call. `TOOL_LOOP_LIMIT` means an actual loop
> limit only; a duplicated `call_id` is never executed twice.
>
> **Phase 9.3 (implemented).** Completed tool results are persisted through a
> `ToolExecutionStore` keyed by `(inference_session_id, call_id)` (in-memory and
> SQLite backends), and a resumed workflow reuses a completed result instead of
> executing the same call twice.

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
├── apps/            mcp-server/ · research-runtime/ · inference-runtime/ · dashboard/
├── python/          research/ · reasoning/ · orchestration/ · retrieval/
│                    memory/ · documents/ · verification/ · workflows/
│                    inference/ · computation/
├── rust/            core/ · filesystem/ · indexer/ · search/ · process/
├── typescript/      dashboard/
├── schemas/         domain/ · mcp/ · inference/
├── data/            database/ · index/ · memory/ · cache/ · sessions/
├── corpus/          sources/ · papers/ · books/ · notes/ · datasets/
│                    projects/ · archive/
├── workflows/  prompts/  config/  tests/  scripts/  docs/
├── ARCHITECTURE.md  SECURITY.md  README.md  pyproject.toml  .env.example
```

This is a **logical structure**, not an instruction to create every directory
now. The `apps/` entries are **logical runtimes**, not three mandatory network
daemons — initially they may be one executable, one Python package, and one
Rust library.

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
| [runtime-boundaries](docs/architecture/runtime-boundaries.md) | MCP Server / Research Runtime / Inference Runtime separation |
| [execution-model](docs/architecture/execution-model.md) | Per-mode execution paths |
| [domain-contracts](docs/architecture/domain-contracts.md) | Domain objects, API vs transport, tool abstraction, task state machine |
| [operating-modes](docs/architecture/operating-modes.md) | Inference ownership, CapabilityMode, escalation contract |
| [capability-negotiation](docs/architecture/capability-negotiation.md) | ProviderCapabilities, ReasoningBudget, APPLY/DEGRADE/EMULATE/REJECT |
| [component-boundaries](docs/architecture/component-boundaries.md) | Interfaces, ownership, dependency rules |
| [polyglot-boundaries](docs/architecture/polyglot-boundaries.md) | Language responsibilities, FFI policy |
| [data-flow](docs/architecture/data-flow.md) | Request → response, persistence, state transitions |
| [reasoning-engine](docs/architecture/reasoning-engine.md) | Profiles, workflow engine, iterative passes |
| [mcp](docs/architecture/mcp.md) | Tool surface, permissions, protocol |
| [corpus](docs/architecture/corpus.md) | Corpus roots, security boundary, scanner |
| [document-pipeline](docs/architecture/document-pipeline.md) | Parsers, normalization, chunking, PDF handling |
| [retrieval](docs/architecture/retrieval.md) | Pipeline, ranking, corpus, document pipeline |
| [semantic-retrieval](docs/architecture/semantic-retrieval.md) | Embedding provider, vector index, versioning |
| [hybrid-retrieval](docs/architecture/hybrid-retrieval.md) | Fusion, diversity, reranker, fallback |
| [memory](docs/architecture/memory.md) | Structured persistent memory, provenance, isolation |
| [memory](docs/architecture/memory.md) | Stores, entity model, lifecycle |
| [evidence-integrity](docs/architecture/evidence-integrity.md) | Evidence integrity & verification foundation (Phase 5) |
| [claims](docs/architecture/claims.md) | Claim model, status lifecycle, claim–evidence links |
| [verification](docs/architecture/verification.md) | Verification engine, rules, statuses, coverage |
| [contradictions](docs/architecture/contradictions.md) | Contradiction types, statuses, deterministic detection |
| [computation](docs/architecture/computation.md) | Deterministic computation layer (Phase 6) |
| [duckdb](docs/architecture/duckdb.md) | DuckDB analytics engine and SQL safety |
| [python-sandbox](docs/architecture/python-sandbox.md) | Controlled Python subprocess sandbox |
| [computation-provenance](docs/architecture/computation-provenance.md) | Provenance, freshness, results-as-evidence |
| [orchestration](docs/architecture/orchestration.md) | Research orchestration layer (Phase 7) |
| [planning](docs/architecture/planning.md) | Deterministic task classification and planning |
| [workflows](docs/architecture/workflows.md) | Workflow engine and stage executors |
| [research-state-machine](docs/architecture/research-state-machine.md) | Task/plan/run/state ownership and lifecycle |
| [inference](docs/architecture/inference.md) | Provider abstraction, policy translation, capability negotiation |
| [inference-runtime](docs/architecture/inference-runtime.md) | Provider-neutral Inference Runtime (Phase 8) |
| [providers](docs/architecture/providers.md) | Provider abstraction & configuration |
| [qwen-provider](docs/architecture/qwen-provider.md) | Qwen backend adapter |
| [tool-loop](docs/architecture/tool-loop.md) | Controlled model ↔ tool-call loop (Phase 9) |
| [inference-continuation](docs/architecture/inference-continuation.md) | Inference continuation & preserved reasoning state |
| [hybrid-mode](docs/architecture/hybrid-mode.md) | Hybrid Studio/Gateway boundary contract |
| [security](docs/architecture/security.md) | Threat model, boundaries, sandboxing |
| [architecture-review](docs/architecture/architecture-review.md) | Risks, failure modes, Rust-value analysis |
| [implementation-phases](docs/architecture/implementation-phases.md) | Phase 0–12 roadmap |
| [mcp-implementation](docs/architecture/mcp-implementation.md) | Phase 2 MCP server foundation |
| [phase-1-contracts](docs/architecture/phase-1-contracts.md) | Phase 1 deliverables and non-goals |
| [domain-model](docs/architecture/domain-model.md) | Domain objects, state machine, errors, serialization |
| [runtime-contracts](docs/architecture/runtime-contracts.md) | Research Runtime, tools, workflows, inference, persistence |
| [decisions/](docs/architecture/decisions/) | ADRs for major architectural decisions |
| [diagrams/](docs/architecture/diagrams/) | Mermaid diagrams |
