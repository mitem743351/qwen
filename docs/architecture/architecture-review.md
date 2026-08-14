# Architecture Review

A critical review of the architecture before any implementation begins. This
identifies ambiguities, risks, failure modes, and the places where the polyglot
strategy genuinely pays off — versus where it would be overengineering.

---

## 1. Architectural Ambiguities (to resolve before Phase 1)

| Ambiguity | Why it matters | Proposed resolution |
|-----------|----------------|---------------------|
| Exactly which MCP SDK/protocol version | Affects the entrypoint contract | Adopt a specific SDK at Phase 2; keep it behind a thin façade so it can be swapped |
| Embedding model & vector store choice | Affects retrieval but is deliberately deferred | Abstract `VectorIndex` + `Embedder`; pick a default at Phase 3 |
| "Project" definition (what auto-creates one) | Affects memory scoping | Projects are explicit user-created scopes; sessions default to a "default project" |
| How complexity assessment is calibrated | Affects profile selection correctness | Deterministic rubric + bounded enum, tuned with an eval harness at Phase 4 |
| Where Rust actually earns its place | Risk of premature Rust | Decide per-capability at Phase 3/7 based on profiling (see §5) |
| Checkpoint granularity | Affects resumability cost | Stage-level checkpoints (not token-level) as the default |
| Whether the dashboard shares a process | Affects TypeScript coupling | Separate read-only observability process; never a core dependency |

These are not open-ended; each has a stated default that later phases confirm
or overturn **via a decision record**, not silently.

---

## 2. Dependency Risks

| Dependency | Risk | Mitigation |
|------------|------|------------|
| Qwen backend/API | Provider changes or deprecates parameters | Everything above `InferenceProvider` is provider-neutral; adapters absorb change |
| A specific MCP SDK | API drift | Façade layer; semantic tools are SDK-agnostic |
| Embedding model | Quality/size/cost changes | `Embedder` interface; re-indexable corpus |
| DuckDB/Python runtime versions | Compatibility | Pinned, isolated environment; reproducible `pyproject.toml` |
| Rust toolchain | Build friction for contributors | Rust limited to justified, isolated crates with clear FFI boundary |

---

## 3. Unnecessary Complexity (deliberately avoided)

- **No microservices.** One gateway process; subsystems are in-process modules.
- **No three databases in v1.** SQLite (system-of-record) + DuckDB (analytics)
  only; PostgreSQL deferred.
- **No agent swarm / computer-use / distributed agents.** Trajectory interfaces
  only.
- **No universal tool.** A small, semantic MCP surface.
- **No Rust for its own sake.** Only where profiling justifies it.
- **No auth system in v1.** Single-user local-first.

---

## 4. Failure-Mode Inventory

### Retrieval failure modes

- Vocabulary gap → hybrid fusion (lexical+semantic+metadata).
- Semantic drift → reranking + evidence threshold.
- Disconfirming evidence hidden → verification runs independent counterexample search.
- Parse failures → structured error, RAW retained, flagged.

### Reasoning failure modes

- Stage looping → budgeted passes/attempts in the profile.
- Contradiction found → loop to retrieve/reason or record unresolved question.
- Context overflow → Context Engine compacts and prioritizes; no silent truncation.
- Interruption → stage-level checkpoints, resumable.

### State-management risks

- Memory bloat → scoped reads + compaction budgets.
- Stale claims → claims reference source hash; re-verify on source change.
- Cross-session bleed → every read scoped by project/session.

### Context-management risks

- Loss of disconfirming evidence → context assembly is verification-aware.
- Prompt concatenation drift → Context Engine is the only assembler.
- Budget exhaustion → allocation policy per task component, not a single blob.

### Security risks

- Prompt injection via corpus → corpus treated as data; permissions gate all tools.
- Sandbox escape → OS-level isolation, no-network default, resource limits.
- Secret leakage → redaction + secret isolation + audit.

### Provider lock-in

- The only provider-specific code is inside adapters. The translation layer
  (`ReasoningProfile → InferencePolicy → params`) is the seam that absorbs
  backend changes.

---

## 5. Where Rust Provides Genuine Value (vs. overengineering)

**Genuine value (justified):**

- Filesystem scanning & indexing of large corpus trees (GIL-free parallelism).
- Hashing (content addressing) at ingest.
- File watching for index freshness.
- High-throughput lexical/phrase search at scale.
- Sandbox/process management (precise resource control, safety).
- Long-lived concurrent MCP server (only if load demands).

**Overengineering (keep Python):**

- Workflow/reasoning orchestration.
- PDF/Office parsing (Python library ecosystem is superior; I/O-bound).
- Metadata extraction (library-driven).
- Verification logic (experimental, model-adjacent).
- Inference adapters (network I/O-bound).
- DuckDB orchestration (DuckDB is already native).

**Decision rule:** profile first; choose Rust only for a demonstrated
single-machine performance/safety need. The FFI boundary (PyO3) is the
mechanism, so moving a hot path Python → Rust is a **contained, reversible**
change.

---

## 6. Where Python Is Clearly Correct

Reasoning orchestration, workflow logic, agent logic, retrieval orchestration,
document processing, metadata, embeddings, reranking, verification, inference
adapters, evaluation, data science, research workflows, experimental
algorithms — everything model-adjacent or fast-changing.

---

## 7. Likely Scaling Bottlenecks (acknowledged, not yet optimized)

1. **Ingest throughput** on very large corpora → Rust indexer (deferred).
2. **Semantic index size/memory** → vector backend choice (deferred).
3. **Model context window** → Context Engine budgeting + compaction (core now).
4. **Long-output coherence** → sectioned generation + assembly ledger (core now).
5. **Single-process CPU contention** (verification + rerank + compute) → measured
   later; parallelism is a profile dial, not an assumption.

---

## 8. Future Extension Points (seams, not code)

| Extension | Seam |
|-----------|------|
| Local Qwen / alternative providers | New `InferenceProvider` adapter |
| New document types | New `Parser` adapter |
| New corpus folders | Config-driven discovery (folders are data) |
| New tools | Registered, permission-scoped MCP tools |
| New verification checks | Registered `Verifier` |
| PostgreSQL | New repository implementations |
| Parallel trajectories | `Trajectory` interface (established now) |
| Dashboard | Read-only observability interface |
| Distributed workers | Later; the gateway's manager interfaces are the boundary |

---

## 9. Verdict

The architecture is **internally consistent** for Phase 0: concerns are
separated, layers are decoupled, the inference seam absorbs provider risk, the
memory/context/verification split prevents reasoning-from-prompt-only, and the
polyglot strategy is bounded by a "profile first" rule. The remaining work is
to lock the few Phase-0 ambiguities (§1) into defaults and proceed to Phase 1.
