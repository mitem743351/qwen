# Implementation Phases

The roadmap from architecture (Phase 0) through optimization (Phase 12). Each
phase lists objective, dependencies, major components, acceptance criteria, and
explicit **not-yet** items. Phase 1 must not begin until Phase 0 (and the
0.5 / 0.75 corrections) are internally consistent.

> **Note on numbering.** The delivered sequence advanced the *verification
> foundation* as **Phase 5** (after Phase 4 semantic/memory and Phase 4.1
> hardening) ahead of the originally-planned "Reasoning/workflow engine"
> (roadmap §Phase 5 below). The roadmap's §Phase 5 (workflow engine) therefore
> remains **not-yet**, while its §Phase 6 (Verification) is partially realized —
> the deterministic baseline (claims, evidence, source quality, corroboration,
> contradiction analysis) is delivered; the model-assisted / multi-agent /
> web fact-checking parts remain future.

---

## Phase 0 — Architecture ✅ (complete)

- **Objective:** stable architecture contract.
- **Dependencies:** none.
- **Components:** all documents in this directory, ADRs, diagrams.
- **Acceptance criteria:** every concern separated; provider seam defined;
  retrieval/reasoning/computation/memory boundaries unambiguous; ADRs for major
  decisions.
- **Not yet:** any runtime code.

## Phase 0.5 — Inference ownership ✅ (complete)

- **Objective:** explicit inference ownership and operating modes.
- **Dependencies:** Phase 0.
- **Components:** `CapabilityMode` (STUDIO_NATIVE / GATEWAY_INFERENCE / HYBRID),
  capability matrix, `ReasoningBudget`, escalation contract, ADRs 0014–0017.
- **Acceptance criteria:** no document implies MCP controls Studio inference;
  XHIGH/EXTREME qualified per mode.
- **Not yet:** any runtime code.

## Phase 0.75 — Runtime boundaries ✅ (complete)

- **Objective:** MCP Server / Research Runtime / Inference Runtime separation.
- **Dependencies:** Phase 0.5.
- **Components:** runtime boundary docs, execution model, domain contracts,
  runtime contracts, Internal Tool Registry, task state machine, ADRs 0018–0023.
- **Acceptance criteria:** dependency direction unambiguous; no monolithic
  "gateway"; MCP is an adapter; runtimes are logical, not three daemons.
- **Not yet:** any runtime code.

---

## Phase 1 — Core domain/runtime contracts ✅ (complete)

- **Objective:** transport-neutral domain model and runtime contracts, defined
  and testable.
- **Dependencies:** Phase 0.75.
- **Components:** domain objects (`Task`, `Session`, `ResearchState`, `Source`,
  `Evidence`, `Claim`, `Artifact`, `Workflow`, `ReasoningProfile`,
  `ReasoningBudget`, `InferencePolicy`/`Request`/`Result`, `ProviderCapabilities`,
  `VerificationResult`); `ResearchRuntime` API protocol + `InMemoryResearchRuntime`;
  `MCPRequest`/`MCPResult`; internal `Tool` abstraction + `ToolRegistry`;
  `Workflow` contracts + `WorkflowRegistry`; `InferenceProvider` protocol;
  repository protocols + in-memory stores; task state machine; typed errors;
  deterministic version-aware serialization; configuration model.
- **Acceptance criteria:** 58 tests pass (unit + contract + vertical slice);
  `ruff` and `mypy` clean; domain model has no MCP/Qwen/HTTP/database imports;
  `retrieve_context`/`verify_claim` raise `UnsupportedOperationError` (no
  fabricated results).
- **Not yet:** MCP server, retrieval, embeddings, real providers, sandbox,
  real persistence.

## Phase 2 — MCP Server foundation ✅ (complete)

- **Objective:** STUDIO_NATIVE mode is real — the MCP Server adapter is live.
- **Dependencies:** Phase 1 (and 1.1/1.2 hardening).
- **Components:** MCP Server over the official `mcp` SDK (stdio transport);
  `MCPTransport` abstraction; schema adapters (MCP ↔ domain); permission model
  (`ToolPermissionPolicy`); error normalization (`map_error`); six tools
  (`get_session`, `create_session`, `execute_task`, `continue_task`,
  `get_task_state`, `get_research_state`); lifecycle + diagnostics; a real
  stdio integration test.
- **Acceptance criteria:** server starts/stops cleanly; client initializes and
  discovers tools; all six tools work through MCP; errors are safely
  normalized; permissions enforced; session/task isolation enforced;
  local-only default; Research Runtime and Domain remain MCP-free.
- **Not yet:** `search_corpus`/`retrieve_evidence`/`verify_claim`/`run_analysis`
  tools; MCP resources; SSE/HTTP transports; remote transport/auth;
  GATEWAY_INFERENCE/HYBRID; dashboard.

## Phase 3 — Corpus + retrieval ✅ (complete — lexical foundation)

- **Objective:** local corpus ingestion, indexing, and retrieval.
- **Dependencies:** Phase 1–2.
- **Components:** `corpus/` (config, security, scanner, hashing, records);
  `documents/` (pluggable parsers: text/markdown/code/json/yaml/csv/pdf,
  normalization, chunking); `indexing/` (CorpusIndex interface, SQLite+FTS5,
  schema, incremental manager); `retrieval/` (Retriever interface,
  LexicalRetriever, evidence packaging); Research Runtime `search_corpus` /
  `get_source`; MCP `search_corpus` / `get_source` tools; typed corpus errors.
- **Acceptance criteria:** configured roots; path/symlink security; incremental
  + idempotent indexing; PDF text extraction (unextractable flagged); chunk
  provenance; FTS5 ranked retrieval; evidence packaging; retrieval MCP tools;
  existing tools intact; no unrestricted filesystem access; prompt-injection
  boundary respected.
- **Not yet:** verification; deep workflows; embeddings/vector search;
  reranking; hybrid retrieval; OCR; Office parsing; Rust indexer.

## Phase 4 — Semantic retrieval + persistent memory ✅ (complete)

- **Objective:** semantic + hybrid retrieval and persistent structured memory.
- **Dependencies:** Phase 1–3.
- **Components:** `EmbeddingProvider` abstraction + `HashingEmbeddingProvider`
  (deterministic, offline); `VectorIndex` + `SqliteVectorIndex` (brute-force
  cosine); `EmbeddingManager` (incremental, versioned); `SemanticRetriever`;
  `HybridRetriever` (RRF fusion + diversity + optional reranker); memory domain
  objects + six repository interfaces + `SqliteMemoryStore`; `MemoryRetriever`;
  `ResearchContext`/`build_context`; Research Runtime memory methods; MCP tools
  (`search_corpus(mode=…)`, `get_project_memory`, `get_research_memory`,
  `get_open_questions`, `save_research_memory`).
- **Acceptance criteria:** lexical + semantic + hybrid retrieval; deterministic
  fusion; incremental embeddings; versioned vectors (no mixing); project/session
  memory isolation; provenance; bounded context assembly; graceful semantic
  fallback; persistence across restart.
- **Not yet:** knowledge-graph DB; PostgreSQL; transformer embeddings; ANN
  vector index; cross-encoder reranker; verification; deep workflows.

## Phase 5 — Evidence integrity & verification foundation ✅ (complete)

- **Objective:** deterministic evidence-integrity and verification baseline.
- **Dependencies:** Phase 3–4.1 (retrieval + memory provenance).
- **Components:** `claims/` (structured `Claim`, `ClaimStatus`, `ClaimType`,
  `Scope`, `QuantitativeClaim`, `ClaimEvidenceLink`); `evidence/`
  (`EvidenceRecord`, `SupportType`, `ExtractionQuality`, `EvidenceQuality`);
  `sources/` (`SourceTier` TIER_1..TIER_5, `SourceQualityAssessor`,
  `assess_independence`); `contradictions/` (types/statuses/severities,
  deterministic `assess_contradiction`/`detect_contradiction(s)`);
  `verification/` (`VerificationEngine`, 10 deterministic rules,
  `VerificationStatus`/`Coverage`/`VerificationReport`, `EvidenceIntegrityService`,
  `SqliteVerificationStore`); Research Runtime methods; MCP tools (`create_claim`,
  `link_claim_evidence`, `assess_evidence`, `verify_claim`,
  `get_verification_report`, `get_contradictions`); typed verification errors.
- **Acceptance criteria:** claim/evidence/source/contradiction/report models
  persisted and restored across restart; project isolation; atomic
  reference-validated writes; deterministic statuses bounded by
  `VERIFIED_WITHIN_CORPUS` (never absolute truth); corroboration at source
  level (not chunk level); `UNREVIEWED` never silently promoted.
- **Not yet:** LLM claim extraction, LLM contradiction reasoning, LLM
  source-quality judgment, web fact-checking, multi-agent verification,
  adversarial debate (Phase 10), deep-workflow auto-verification loops.

## Phase 5 (roadmap) — Reasoning/workflow engine

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

> **Partial delivery (Phase 5).** The deterministic baseline (claims, evidence,
> source quality, corroboration, contradiction analysis, `verify_claim` /
> `get_contradictions` tools, persisted reports) is delivered in the actual
> Phase 5. Remaining here: counterexample search, calculation validation,
> cross-document consistency at scale, and deep-workflow auto-verification
> loops (the model-assisted layer sits behind `VerificationAssistant`).

## Phase 6 — Deterministic computation & sandboxed analysis ✅ (complete)

- **Objective:** bounded, provenance-bearing computation (DuckDB + sandboxed Python).
- **Dependencies:** Phase 3 (corpus security), Phase 4 (memory), Phase 5 (verification).
- **Components:** `computation/` (domain model, `ComputationEngine`, execution
  registry, `DuckDBBackend` behind `AnalyticsEngine`, `PythonExecutor` subprocess
  sandbox, seeded simulation, pure-stdlib statistics, artifact store, SQLite
  metadata store); Research Runtime methods; MCP tools (`describe_dataset`,
  `run_query`, `run_analysis`, `get_computation_result`, `run_python`);
  typed computation errors; memory `computation_refs`/`dataset_refs`.
- **Acceptance criteria:** structured results with provenance (query/code
  hashes, dataset freshness); execution profiles + resource limits; SQL cannot
  escape approved datasets; Python cannot access files/network/processes; large
  results become artifacts; restart persistence; security escape tests pass.
- **Not yet:** Rust/GPU/remote backends; automatic numerical correctness
  proving; hardened (seccomp/container) Python isolation.

## Phase 7 — Research orchestration & workflow execution ✅ (complete)

- **Objective:** turn individual capabilities into a deterministic research
  orchestration system.
- **Dependencies:** Phases 3–6 (retrieval, memory, verification, computation).
- **Components:** `orchestration/` — `ResearchTask`/`ResearchPlan`/
  `WorkflowRun`/`WorkflowEvent` models, deterministic `ResearchPlanner`
  (classification, complexity, templates, budgets), `WorkflowEngine` with
  registered `StageExecutor`s (retrieve → assess → verify → compute → memory →
  synthesize → finalize), bounded loops, retry policies, idempotency, resource
  accounting, `OrchestrationStore` (SQLite), `SynthesisRequest` boundary, MCP
  tools (`plan_research`, `start_research`, `get_research_status`, `pause`,
  `resume`, `cancel`, `get_research_summary`).
- **Acceptance criteria:** deterministic classification/planning; resumable
  workflow state across restart; pause/resume/cancel at the orchestration level;
  explicit retry + idempotency; bounded evidence/verification/computation loops;
  retrieval/verification/computation/memory integration; bounded
  `ResearchContext` synthesis; no inference provider invoked.
- **Not yet:** model-assisted planning; parallel model trajectories; automatic
  web research; the inference-runtime connection (Phase 8).

## Phase 7 (roadmap) — Computation/tools

- **Objective:** deterministic computation + internal tool registry.
- **Dependencies:** Phase 1–2 (sandbox), Phase 3 (data access).
- **Components:** Python sandbox executor (no-network, resource limits); DuckDB
  service; Internal Tool Registry; `run_analysis`; allowlists.
- **Acceptance criteria:** model requests/interprets computations; no secret or
  allowlist escape; tools callable from CLI/API, not only MCP.
- **Not yet:** remote compute; GPU workflows.

> **Partial delivery (Phase 6).** The deterministic computation baseline
> (DuckDB analytics, controlled Python sandbox, provenance, MCP tools) is
> delivered in the actual Phase 6. Remaining here: the full Internal Tool
> Registry-driven `run_analysis` dispatch, and hardened OS-level isolation.

## Phase 8 — Inference Runtime ✅ (complete)

- **Objective:** GATEWAY_INFERENCE mode is real (single reliable inference call).
- **Dependencies:** Phase 1–5.
- **Components:** `InferenceRuntime` (provider selection, capability
  negotiation, request validation, retries, timeouts, usage accounting,
  response normalization); `InferenceRouter`; `ModelRegistry`;
  `SqliteInvocationStore`; `QwenProvider` (OpenAI-compatible adapter with
  injectable transport, credential handling, streaming, structured output,
  tool-call representation); `synthesis_to_inference` adapter; Research Runtime
  `invoke_inference` / `stream_inference` / `synthesize`.
- **Acceptance criteria:** provider swap changes no workflow code; unsupported
  capabilities negotiated and recorded; credentials isolated from domain/MCP;
  hidden reasoning never persisted; single-invocation GATEWAY_INFERENCE flow
  works end-to-end; provider contract + fake-transport tests pass.
- **Not yet:** local Qwen / alternative providers (interfaces ready); iterative
  tool loops (Phase 9); hybrid escalation (Phase 9); XHIGH/EXTREME
  orchestration (Phase 10).

## Phase 8.1 — Qwen contract currency & model specificity ✅ (complete)

- **Objective:** make Qwen capability discovery/model mapping current and
  model-specific; implement `thinking_budget`; represent full tool schemas;
  validate structured output against the requested schema; implement real
  stream-idle semantics; refresh the 2026 API documentation.
- **Dependencies:** Phase 8.
- **Components:** `qwen_models.py` model catalog (`QwenModelSpec`);
  model-specific `capabilities(model)`/`limits(model)`/`model_info(model)`/
  `models()`; `ToolSpec` (name + description + argument JSON Schema) replacing
  bare tool names; `thinking_budget` emission on Qwen3-era thinking models;
  `schema_validation.py` (bounded JSON Schema validator); incremental
  `HttpTransport.stream` with `stream_idle_seconds` idle timeout; default model
  raised to `qwen3.7-max`.
- **Acceptance criteria:** per-model capabilities/context windows; numeric
  thinking budget emitted only where supported; complete tool schemas passed
  through; schema-nonconforming structured output rejected; a stalled stream
  raises `ProviderTimeoutError`; docs reflect the current contract.
- **Not yet:** tool **execution** (Phase 9); hybrid escalation (Phase 9);
  XHIGH/EXTREME orchestration (Phase 10).

## Phase 8.2 — Qwen catalog model-specificity & verification ✅ (complete)

- **Objective:** make `preserve_thinking`, `structured_output`, `tool_calling`,
  and `streaming` model-specific; remove unverified entries; pin `qwen3.7-max`
  against official docs; establish catalog maintenance.
- **Dependencies:** Phase 8.1.
- **Components:** `QwenModelSpec` gains `preserve_thinking`,
  `structured_output`, `tool_calling`, `streaming`; `capabilities(model)` maps
  each from the catalog; `preserve_thinking` emitted on `qwen3.7-max` /
  `qwen3.7-plus`; `qwen3.8-max` removed as unverified; `qwq-*` marked
  thinking-only (no structured output / tool calling); `qwen3.7-max` pinned
  (1M context, 65,536 max output, thinking + budget + preserve_thinking);
  catalog-maintenance process documented.
- **Acceptance criteria:** per-model preserve/structured/tool/stream
  capabilities; `qwen3.8-max` absent; `qwen3.7-max` documented facts asserted
  in tests; official-doc sources recorded in the catalog.
- **Not yet:** tool **execution** (Phase 9); hybrid escalation (Phase 9);
  XHIGH/EXTREME orchestration (Phase 10).

## Phase 8.3 — Qwen model availability & endpoint awareness ✅ (complete)

- **Objective:** make Qwen model availability and capability resolution
  contextual (model + endpoint + region + plan + inference mode) rather than
  globally hard-coded.
- **Dependencies:** Phase 8.2.
- **Components:** `QwenModelSpec` extended (aliases, lifecycle, availability,
  plans, regions, surfaces, input/thinking bounds, `thinking_always_enabled`,
  `parallel_tool_calling`, `context_caching`, built-in tools,
  `reasoning_effort_levels`, notes, source URLs); `qwen_availability.py`
  (`QwenApiSurface`, `QwenEndpointProfile`, `AvailabilityStatus`/`Result`,
  `QwenModelAvailabilityResolver`, `ModelDiagnostic`, standard + Token Plan
  endpoint profiles); provider `capabilities(model, thinking_mode=…)` /
  `limits` / `model_info` / `diagnose`; distinct availability errors
  (`UnknownModelError`, `ModelPlanUnavailableError`, `ModelRegionUnavailableError`,
  `ModelEndpointUnavailableError`, `EndpointCapabilityError`); `qwen3.8-max-preview`
  cataloged as PREVIEW / PLAN_RESTRICTED / Token Plan; `ModelRegistry` plan/region
  filtering; runtime passes inference-mode intent into negotiation.
- **Acceptance criteria:** availability contextual; `qwen3.8-max-preview`
  represented (not removed); Token Plan / endpoint / region restrictions
  represented; effective capabilities depend on model + mode; function calling
  vs built-in tools kept separate; unknown models usable conservatively;
  distinct availability errors; capability-matrix regression test passes.
- **Not yet:** tool **execution** (Phase 9); hybrid escalation (Phase 9);
  XHIGH/EXTREME orchestration (Phase 10); Qwen built-in tool invocation.

## Phase 8.4 — Qwen endpoint control & transient reasoning state ✅ (complete)

- **Objective:** make the endpoint profile control/validate the network
  endpoint; add transient `reasoning_content` for multi-turn continuation;
  correct `qwen3.8-max-preview` context to 983,616; prove Token Plan vs
  standard-endpoint availability are not conflated; prove multi-turn reasoning
  state is never silently dropped; mark `reasoning_effort` cataloged-only.
- **Dependencies:** Phase 8.3.
- **Components:** `_endpoint()` uses the endpoint profile's `base_url` (and
  rejects a conflicting `api_endpoint`); `Message.reasoning_content` (transient,
  non-serialized); serializer skips `transient` fields; assistant-message
  `reasoning_content` emission; `_guard_preserved_thinking` raises on missing
  reasoning state; `qwen3.8-max-preview` context 983,616; `reasoning_effort`
  documented as cataloged-not-executed.
- **Acceptance criteria:** endpoint profile drives the HTTP target; reasoning
  content carried transiently but never persisted; Token Plan availability
  tests show it is not standard availability; multi-turn preservation never
  silently drops state; `reasoning_effort` never emitted.
- **Not yet:** tool **execution** (Phase 9); hybrid escalation (Phase 9);
  XHIGH/EXTREME orchestration (Phase 10); Qwen built-in tool invocation;
  `reasoning_effort` execution.

## Phase 9 — Controlled tool-calling loop, continuation, and hybrid boundary ✅ (complete)

- **Objective:** move from a single inference call to controlled model ↔
  Research Runtime interaction; establish the first explicit hybrid boundary.
- **Dependencies:** Phase 1–8.
- **Components:** `research/tool_loop.py` (`ToolExecutionRequest`/`Result`,
  `ToolError`, `ToolExecutionProfile` (READ_ONLY/ANALYSIS/RESEARCH),
  `ToolLoopConfig`, `LoopAccounting`, `InferenceSession`/`Conversation`,
  `run_tool_loop`, authorization + argument validation + repeated-call guard);
  `research/model_tools.py` (model-callable tool registry, `run_python`
  excluded); `research/hybrid.py` (`EscalationRequest`/`Result`,
  `validate_transfer`); `Tool.model_callable` flag; Research Runtime
  `run_tool_loop`; transient `reasoning_content` on `InferenceResult`.
- **Acceptance criteria:** tool calls normalized, authorized, validated, and
  executed through the internal registry; the provider never executes tools;
  same inference session continues; hidden reasoning stays transient; hard
  loop limits; repeated-call guard; bounded/artifactized tool results; trusted
  project/session scope; default profile excludes WRITE/EXECUTE/DESTRUCTIVE;
  end-to-end fake-provider tool loop works; hybrid contract defined without
  automatic escalation.
- **Not yet:** automatic escalation heuristics; XHIGH/EXTREME workflows;
  parallel model trajectories; multi-agent inference; Qwen built-in web search;
  `reasoning_effort` execution; remote/distributed workers.

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
