# Implementation Phases

The roadmap from architecture (Phase 0) to optimization (Phase 11). Each phase
lists objective, dependencies, major components, acceptance criteria, and
explicit **not-yet** items. Phase 1 must not begin until Phase 0 (and the
Phase 0.5 corrections) are internally consistent.

### Operating-mode prerequisites (what each mode requires)

| Mode | Requires | Delivered by |
|------|----------|--------------|
| `STUDIO_NATIVE` | MCP, local capability tools, retrieval, memory, verification, artifact handling | Phases 2–7 (no inference adapter) |
| `GATEWAY_INFERENCE` | All of the above **plus** `InferenceProvider`, provider adapters, capability negotiation, policy translation, workflow execution, continuation | Phase 8 |
| `HYBRID` | All of the above **plus** escalation contract, session handoff, context transfer, state synchronization | Phase 9 |

None of these are implemented yet.

---

## Phase 0 — Architecture ✅ (this phase)

- **Objective:** stable architecture contract.
- **Dependencies:** none.
- **Components:** all documents in this directory, ADRs, diagrams.
- **Acceptance criteria:** every concern separated; provider seam defined;
  retrieval/reasoning/computation/memory boundaries unambiguous; inference
  ownership modeled (`STUDIO_NATIVE`/`GATEWAY_INFERENCE`/`HYBRID`); ADRs for
  major decisions; review identifies and resolves ambiguities.
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

## Phase 2 — MCP foundation (⇒ STUDIO_NATIVE mode becomes real)

- **Objective:** the narrow semantic tool surface is live and permission-gated,
  delivering **STUDIO_NATIVE** mode.
- **Dependencies:** Phase 1.
- **Components:** MCP entrypoint (façade over SDK); tool registry; permission
  boundary (`read/analyze/write/execute/destructive`); argument/result schemas;
  audit logging; `CapabilityMode` + mode selector (binding to `STUDIO_NATIVE`
  only at this phase).
- **Acceptance criteria:** tools registered and callable; permission classes
  enforced; a denied `write`/`destructive` call returns a structured denial and
  is audited; **no inference adapter is exercised** (Studio owns inference).
- **Not yet:** tool implementations beyond stubs; dashboard; auth;
  `GATEWAY_INFERENCE`/`HYBRID` modes.

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

## Phase 8 — Inference abstraction (⇒ GATEWAY_INFERENCE mode becomes real)

- **Objective:** provider seam fully realized, delivering **GATEWAY_INFERENCE**
  mode.
- **Dependencies:** Phase 1–4.
- **Components:** `QwenProvider`, `QwenCompatProvider` adapters;
  `ReasoningProfile → InferencePolicy → capability negotiation → params`
  translation; `ProviderCapabilities` + `APPLY`/`DEGRADE`/`EMULATE`/`REJECT`
  outcomes; token usage capture.
- **Acceptance criteria:** swapping providers changes no reasoning/workflow
  code; unsupported capabilities are negotiated and recorded; the gateway now
  genuinely owns the inference loop **and no other mode claims to**.
- **Not yet:** local Qwen / alternative providers (interfaces are ready).

---

## Phase 9 — Advanced XHigh / EXTREME workflows (⇒ HYBRID escalation)

- **Objective:** the high-effort profiles behave as designed, and **HYBRID**
  mode becomes real via the escalation contract.
- **Dependencies:** Phase 4–6, 8.
- **Components:** iterative multi-pass reasoning; critique→correct→verify
  loops; counterargument generation; optional parallel trajectories
  (A–E) behind the `Trajectory` interface; long-output assembly at scale;
  `EscalationRequest`/`EscalationResult` handoff, session handoff, context
  transfer, and state synchronization.
- **Acceptance criteria:** `XHIGH`/`EXTREME` produce verifiably deeper,
  cited, contradiction-checked output than `DEEP`, within budgeted cost;
  an escalated task moves cleanly from Studio-native context into
  gateway-owned workflow and back.
- **Not yet:** distributed agents (trajectories remain in-process);
  automatic escalation heuristics (escalation stays explicit).

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
