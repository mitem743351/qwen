# Implementation Phases

The roadmap from architecture (Phase 0) to optimization (Phase 11). Each phase
lists objective, dependencies, major components, acceptance criteria, and
explicit **not-yet** items. Phase 1 must not begin until Phase 0 is internally
consistent.

---

## Phase 0 — Architecture ✅ (this phase)

- **Objective:** stable architecture contract.
- **Dependencies:** none.
- **Components:** all documents in this directory, ADRs, diagrams.
- **Acceptance criteria:** every concern separated; provider seam defined;
  retrieval/reasoning/computation/memory boundaries unambiguous; ADRs for major
  decisions; review identifies and resolves ambiguities.
- **Not yet:** any runtime code.

---

## Phase 1 — Core skeleton

- **Objective:** a runnable, empty but correctly-shaped system.
- **Dependencies:** Phase 0.
- **Components:** repository/package layout; `InferenceProvider` protocol and
  `ReasoningProfile`/`InferencePolicy` dataclasses; gateway component stubs with
  interfaces; storage repository interfaces (SQLite default); config loading;
  structured logging.
- **Acceptance criteria:** imports resolve; interfaces defined in `python/`;
  a no-op "hello" workflow runs end-to-end against a fake provider.
- **Not yet:** real MCP server, retrieval, embeddings, sandbox, verification
  logic, real providers.

---

## Phase 2 — MCP foundation

- **Objective:** the narrow semantic tool surface is live and permission-gated.
- **Dependencies:** Phase 1.
- **Components:** MCP entrypoint (façade over SDK); tool registry; permission
  boundary (`read/analyze/write/execute/destructive`); argument/result schemas;
  audit logging.
- **Acceptance criteria:** tools registered and callable; permission classes
  enforced; a denied `write`/`destructive` call returns a structured denial and
  is audited.
- **Not yet:** tool implementations beyond stubs; dashboard; auth.

---

## Phase 3 — Corpus + retrieval

- **Objective:** immutable corpus with a working retrieval pipeline.
- **Dependencies:** Phase 1–2.
- **Components:** document pipeline (discovery→index); corpus layout;
  hashing/immutability; lexical + metadata indexes; `VectorIndex`/`Embedder`
  interfaces with a chosen default; hybrid ranking + reranking; evidence
  extraction + citation resolution; context assembly.
- **Acceptance criteria:** ingesting a mixed corpus yields searchable, cited
  evidence; RAW is never modified; a `search_corpus`/`retrieve_evidence` tool
  returns typed evidence records.
- **Not yet:** verification; deep reasoning workflows; Rust indexer (unless
  profiling at this phase justifies it).

---

## Phase 4 — Reasoning engine

- **Objective:** profile-driven workflows actually run.
- **Dependencies:** Phase 1–3.
- **Components:** Task Router (intent + complexity); Reasoning Policy Engine
  (profiles FAST→EXTREME); Task Decomposer; Workflow Engine (stage state
  machine, skip/repeat, checkpoint/resume); Context Engine (budgeting,
  compaction, restore); long-output strategies.
- **Acceptance criteria:** `FAST`/`NORMAL`/`DEEP` run the correct stage
  sequences; a mid-workflow interruption resumes from the last completed stage;
  chain-of-thought is absent from all persisted state.
- **Not yet:** verification-driven loops (Phase 6), full `XHIGH`/`EXTREME`
  parallel trajectories (Phase 9).

---

## Phase 5 — Memory

- **Objective:** the six differentiated stores are operational.
- **Dependencies:** Phase 1–4.
- **Components:** Memory Manager; repositories for sessions/tasks/claims/
  evidence/sources/entities/decisions/questions/artifacts; entity relation
  model; scoped reads; compaction.
- **Acceptance criteria:** research state persists and is retrievable by
  project/session scope; decisions append-only; stale claims re-verify on
  source change.
- **Not yet:** knowledge-base graph DB; PostgreSQL (unless scale demands).

---

## Phase 6 — Verification

- **Objective:** verification is first-class and independently callable.
- **Dependencies:** Phase 3–5.
- **Components:** claim/evidence verification; source quality; contradiction
  detection; counterexample search; citation auditing; calculation validation;
  cross-document consistency; `verify_claim` / `find_contradictions` tools.
- **Acceptance criteria:** deep workflows call verification and can loop on
  failure; verification callable standalone via MCP; outcomes persisted as
  structured state.
- **Not yet:** adversarial critique agents beyond single-pass critique.

---

## Phase 7 — Computation

- **Objective:** deterministic computation separated from reasoning.
- **Dependencies:** Phase 1–2 (sandbox), Phase 3 (data access).
- **Components:** Python sandbox executor (no-network default, resource limits);
  DuckDB service (`query_database`); `run_analysis` tool; allowlist enforcement.
- **Acceptance criteria:** the model requests and interprets computations;
  no computation can touch secrets or escape allowlists; results are audited.
- **Not yet:** arbitrary remote compute; GPU workflows.

---

## Phase 8 — Inference abstraction

- **Objective:** provider seam fully realized.
- **Dependencies:** Phase 1–4.
- **Components:** `QwenProvider`, `QwenCompatProvider` adapters;
  `ReasoningProfile → InferencePolicy → params` translation; `capability_info`
  degradation; token usage capture.
- **Acceptance criteria:** swapping providers changes no reasoning/workflow
  code; unsupported capabilities degrade gracefully and are recorded.
- **Not yet:** local Qwen / alternative providers (interfaces are ready).

---

## Phase 9 — Advanced XHigh / EXTREME workflows

- **Objective:** the high-effort profiles behave as designed.
- **Dependencies:** Phase 4–6, 8.
- **Components:** iterative multi-pass reasoning; critique→correct→verify
  loops; counterargument generation; optional parallel trajectories
  (A–E) behind the `Trajectory` interface; long-output assembly at scale.
- **Acceptance criteria:** `XHIGH`/`EXTREME` produce verifiably deeper,
  cited, contradiction-checked output than `DEEP`, within budgeted cost.
- **Not yet:** distributed agents (trajectories remain in-process).

---

## Phase 10 — Dashboard / observability

- **Objective:** optional TypeScript observability UI.
- **Dependencies:** Phase 4–6 (state exists to observe).
- **Components:** read-only observability interface; session inspection;
  workflow visualization; corpus/artifact browser; system controls.
- **Acceptance criteria:** the core runs fully without the dashboard; the
  dashboard reads only via the observability interface.
- **Not yet:** editing/authoring UI that duplicates Qwen Studio's role.

---

## Phase 11 — Optimization

- **Objective:** targeted performance where profiling justifies it.
- **Dependencies:** all prior phases; profiling data.
- **Components:** Rust indexer/scanner/fast-search **only** where measured;
  vector backend tuning; context/compaction tuning; parallel execution tuning.
- **Acceptance criteria:** each optimization is tied to a measured bottleneck
  and a before/after; no premature generality added.
- **Not yet:** anything that violates "profile first" (§5 of the review).

---

## Ordering Rationale

Phases are ordered so that each phase's **interface dependencies** exist before
it, while deferred choices (embeddings, vector DB, PostgreSQL, Rust indexer,
local models) stay deferred until the seam that isolates them is in place and a
measured need exists. Verification (6) follows memory (5) and retrieval (3)
because verification consumes evidence and persists outcomes; computation (7)
follows the sandbox work seeded in Phase 2.
