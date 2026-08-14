# Implementation Phases

The roadmap from architecture (Phase 0) through optimization (Phase 12). Each
phase lists objective, dependencies, major components, acceptance criteria, and
explicit **not-yet** items. Phase 1 must not begin until Phase 0 (and the
0.5 / 0.75 corrections) are internally consistent.

---

## Phase 0 — Architecture

- **Objective:** stable architecture contract.
- **Dependencies:** none.
- **Components:** all documents in this directory, ADRs, diagrams.
- **Acceptance criteria:** every concern separated; provider seam defined;
  retrieval/reasoning/computation/memory boundaries unambiguous; ADRs for major
  decisions.
- **Not yet:** any runtime code.

## Phase 0.5 — Inference ownership

- **Objective:** explicit inference ownership and operating modes.
- **Dependencies:** Phase 0.
- **Components:** `CapabilityMode` (STUDIO_NATIVE / GATEWAY_INFERENCE / HYBRID),
  capability matrix, `ReasoningBudget`, escalation contract, ADRs 0014–0017.
- **Acceptance criteria:** no document implies MCP controls Studio inference;
  XHIGH/EXTREME qualified per mode.
- **Not yet:** any runtime code.

## Phase 0.75 — Runtime boundaries

- **Objective:** MCP Server / Research Runtime / Inference Runtime separation.
- **Dependencies:** Phase 0.5.
- **Components:** runtime boundary docs, execution model, domain contracts,
  runtime contracts, Internal Tool Registry, task state machine, ADRs 0018–0023.
- **Acceptance criteria:** dependency direction unambiguous; no monolithic
  "gateway"; MCP is an adapter; runtimes are logical, not three daemons.
- **Not yet:** any runtime code.

---

## Phase 1 — Core domain/runtime contracts

- **Objective:** transport-neutral domain model and runtime contracts, defined
  and testable.
- **Dependencies:** Phase 0.75.
- **Components:** domain objects (`Task`, `Session`, `ReasoningProfile`,
  `InferencePolicy`, …); `ResearchRuntime` API protocol;
  `InferenceRequest`/`InferenceResult`; `MCPRequest`/`MCPResult`; `Tool`
  abstraction; repository interfaces (SQLite default); config; structured
  logging.
- **Acceptance criteria:** a Research Runtime unit test runs with a fake
  Inference Runtime; no MCP or Qwen Studio required; domain model has no MCP
  types.
- **Not yet:** MCP server, retrieval, embeddings, real providers, sandbox.

## Phase 2 — MCP Server

- **Objective:** STUDIO_NATIVE mode is real — the MCP Server adapter is live.
- **Dependencies:** Phase 1.
- **Components:** MCP Server (façade over SDK); MCP schema adapters; tool
  registry (MCP view over the Internal Tool Registry); permission boundary;
  audit logging; `CapabilityMode` binding to STUDIO_NATIVE.
- **Acceptance criteria:** tools callable; permissions enforced; domain objects
  adapt to/from MCP without leaking MCP types; **no Inference Runtime on the
  path**.
- **Not yet:** GATEWAY_INFERENCE/HYBRID; dashboard; auth.

## Phase 3 — Corpus + retrieval

- **Objective:** immutable corpus + retrieval pipeline.
- **Dependencies:** Phase 1–2.
- **Components:** document pipeline; corpus layout; hashing; lexical + metadata
  indexes; `VectorIndex`/`Embedder` interfaces; hybrid ranking + reranking;
  evidence extraction + citation resolution; context assembly.
- **Acceptance criteria:** mixed corpus → searchable cited evidence; RAW never
  modified; retrieval callable from the Research Runtime (not just MCP).
- **Not yet:** verification; deep workflows; Rust indexer (unless profiling
  justifies it).

## Phase 4 — Memory + persistence

- **Objective:** differentiated stores + resumable state.
- **Dependencies:** Phase 1–3.
- **Components:** Memory Manager; repositories (sessions/tasks/claims/evidence/
  sources/entities/decisions/questions/artifacts); entity model; scoped reads;
  compaction; task state machine persistence.
- **Acceptance criteria:** research state persists and is resumable by scope;
  decisions append-only; task state machine survives restart.
- **Not yet:** knowledge-graph DB; PostgreSQL (unless scale demands).

## Phase 5 — Reasoning/workflow engine

- **Objective:** profile-driven workflows run.
- **Dependencies:** Phase 1–4.
- **Components:** Task Router; Reasoning Policy Engine (FAST→EXTREME); Task
  Decomposer; Workflow Engine (stage machine, skip/repeat, checkpoint/resume);
  Context Engine; long-output strategies.
- **Acceptance criteria:** FAST/NORMAL/DEEP run correct stages; interruption
  resumes from last completed stage; chain-of-thought absent from state.
- **Not yet:** verification loops (Phase 6), XHIGH/EXTREME trajectories
  (Phase 10).

## Phase 6 — Verification

- **Objective:** verification first-class and independently callable.
- **Dependencies:** Phase 3–5.
- **Components:** claim/evidence verification; source quality; contradiction
  detection; counterexample search; citation auditing; calculation validation;
  cross-document consistency; `verify_claim`/`find_contradictions` tools.
- **Acceptance criteria:** deep workflows loop on verification; standalone via
  MCP and Research Runtime API; outcomes persisted.
- **Not yet:** multi-agent adversarial critique beyond single-pass.

## Phase 7 — Computation/tools

- **Objective:** deterministic computation + internal tool registry.
- **Dependencies:** Phase 1–2 (sandbox), Phase 3 (data access).
- **Components:** Python sandbox executor (no-network, resource limits); DuckDB
  service; Internal Tool Registry; `run_analysis`; allowlists.
- **Acceptance criteria:** model requests/interprets computations; no secret or
  allowlist escape; tools callable from CLI/API, not only MCP.
- **Not yet:** remote compute; GPU workflows.

## Phase 8 — Inference Runtime

- **Objective:** GATEWAY_INFERENCE mode is real.
- **Dependencies:** Phase 1–5.
- **Components:** Inference Runtime (provider routing, capability discovery,
  policy translation, invocation, retries, response normalization);
  `QwenProvider`/`QwenCompatProvider`; `APPLY/DEGRADE/EMULATE/REJECT`
  negotiation; token usage.
- **Acceptance criteria:** provider swap changes no workflow code; unsupported
  capabilities negotiated and recorded; Inference Runtime never calls upward.
- **Not yet:** local Qwen / alternative providers (interfaces ready).

## Phase 9 — Hybrid escalation

- **Objective:** HYBRID mode is real.
- **Dependencies:** Phase 2, 5, 8.
- **Components:** `EscalationRequest`/`EscalationResult` handoff; session
  handoff; context transfer; state synchronization between Studio-native and
  Research-Runtime paths.
- **Acceptance criteria:** an escalated task moves cleanly from Studio context
  into the Research Runtime and back with intact provenance.
- **Not yet:** automatic escalation heuristics (escalation stays explicit).

## Phase 10 — Advanced XHigh / EXTREME workflows

- **Objective:** high-effort profiles behave as designed.
- **Dependencies:** Phase 5–6, 8.
- **Components:** iterative multi-pass reasoning; critique→correct→verify
  loops; counterargument generation; parallel trajectories (A–E) behind
  `Trajectory`; long-output assembly at scale.
- **Acceptance criteria:** XHIGH/EXTREME produce verifiably deeper, cited,
  contradiction-checked output than DEEP, within budgeted cost.
- **Not yet:** distributed agents (trajectories in-process).

## Phase 11 — Dashboard / observability

- **Objective:** optional TypeScript observability UI.
- **Dependencies:** Phase 4–6 (state exists to observe).
- **Components:** read-only observability interface; session inspection;
  workflow visualization; corpus/artifact browser; system controls.
- **Acceptance criteria:** core runs without the dashboard; dashboard reads
  only via the observability interface.
- **Not yet:** editing/authoring UI duplicating Qwen Studio's role.

## Phase 12 — Performance optimization

- **Objective:** targeted optimization where profiling justifies it.
- **Dependencies:** all prior phases; profiling data.
- **Components:** Rust scanner/indexer/fast-search **only where measured**;
  vector backend tuning; context/compaction tuning; parallel execution tuning.
- **Acceptance criteria:** each optimization tied to a measured bottleneck with
  before/after; no premature generality.
- **Not yet:** anything violating "profile first" (§5 of the review).

---

## Operating-mode prerequisites (what each mode requires)

| Mode | Requires | Delivered by |
|------|----------|--------------|
| `STUDIO_NATIVE` | MCP Server, local capability tools, retrieval, memory, verification, artifact handling | Phases 2–7 (no Inference Runtime) |
| `GATEWAY_INFERENCE` | All of the above **plus** Inference Runtime, provider adapters, capability negotiation, policy translation, workflow execution, continuation | Phase 8 |
| `HYBRID` | All of the above **plus** escalation contract, session handoff, context transfer, state synchronization | Phase 9 |

None of these are implemented yet.

---

## Ordering Rationale

Phases are ordered so each phase's **interface dependencies** exist before it,
while deferred choices (embeddings, vector DB, PostgreSQL, Rust indexer, local
models) stay deferred until the seam that isolates them is in place and a
measured need exists. The runtime boundaries (Phase 0.75) are realized
progressively: domain contracts (1) → MCP Server (2) → Research Runtime
capabilities (3–7) → Inference Runtime (8) → escalation (9) → advanced
workflows (10). Verification (6) follows memory (5) and retrieval (3) because
it consumes evidence and persists outcomes; computation (7) follows the
sandbox work seeded in Phase 2.
