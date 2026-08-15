# Qwen Research System

A **local, single-user-first AI research infrastructure** that extends
**Qwen Studio** (via MCP) into a powerful API/agent runtime: configurable
deep-reasoning workflows, long-output generation, a private local corpus,
persistent research memory, verification/citation/provenance, and deterministic
computation — while Qwen Studio keeps its native conversational and web-search
capabilities.

> **Current status: Phase 9.1 — Tool-loop hardening (continuation semantics, malformed-argument rejection).**
> The architecture (Phases 0, 0.5, 0.75) is the approved baseline; Phases 1–1.2
> established and hardened the core contracts; Phases 2–3 added the MCP server
> and lexical corpus retrieval; Phase 4 adds semantic + hybrid retrieval and
> persistent structured memory; Phase 5 adds the deterministic evidence-integrity
> and verification foundation; Phase 6 adds the deterministic computation layer;
> Phase 7 adds the deterministic orchestration layer; Phase 8 adds the real
> provider-neutral Inference Runtime with a Qwen backend; Phases 8.1–8.4 make
> Qwen capability discovery model-specific, current (2026), verified against
> official docs, endpoint/plan/region aware, and endpoint-controlled with
> transient multi-turn reasoning state. Phase 9 adds the controlled model ↔
> tool-call loop and the hybrid Studio/Gateway boundary. Still **no** LLM
> verification, automatic hybrid escalation, XHIGH orchestration, or dashboard.

## What this is

A clean, layered architecture with strict separation between:

- **Qwen Studio** (human interface)
- **MCP Server** (capability exposure boundary)
- **Research Runtime** (workflow, policy, orchestration)
- **Inference Runtime** (provider-facing model execution)
- **Knowledge / Computation / Tools** (capabilities)
- **Local Data** (storage and corpus)

…and between eight concerns: model capability, inference configuration,
reasoning workflow, tool execution, knowledge retrieval, persistent state,
verification, and deterministic computation. `XHIGH`/`EXTREME` reasoning is
modeled as an explicit **workflow/inference policy**, not a longer prompt, and
all model access goes through a provider-independent **inference abstraction**
so the system survives a Qwen backend change.

### Inference ownership (Phase 0.5) and runtime boundaries (Phase 0.75)

The architecture distinguishes **tool augmentation** from **inference
control**, with three operating modes:

- **`STUDIO_NATIVE`** — Qwen Studio owns inference; the local system provides
  MCP tools, corpus, retrieval, memory, computation, verification, artifacts.
- **`GATEWAY_INFERENCE`** — the Research Runtime owns the workflow and the
  Inference Runtime invokes an inference backend through `InferenceProvider`.
- **`HYBRID`** — normal interaction stays in Qwen Studio; selected tasks
  escalate to the Research Runtime.

Three **logically distinct runtimes** replace any monolithic "gateway": the
**MCP Server** (capability exposure), the **Research Runtime**
(provider-independent research/orchestration), and the **Inference Runtime**
(provider-facing model execution) — separate even when deployed in one local
process.

MCP extends a model with **capabilities**; it does not grant control over the
host client's inference parameters. Direct XHIGH-style inference control exists
only where the backend exposes it. See
[`operating-modes.md`](docs/architecture/operating-modes.md) and
[`runtime-boundaries.md`](docs/architecture/runtime-boundaries.md).

## Documentation

Start here:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the binding architecture contract
- [`SECURITY.md`](SECURITY.md) — security posture
- [`docs/architecture/system-overview.md`](docs/architecture/system-overview.md)

Phase 1 implementation:

- [`docs/architecture/phase-1-contracts.md`](docs/architecture/phase-1-contracts.md) — what Phase 1 delivers
- [`docs/architecture/domain-model.md`](docs/architecture/domain-model.md) — the domain objects
- [`docs/architecture/runtime-contracts.md`](docs/architecture/runtime-contracts.md) — the runtime interfaces

Phase 2 (MCP server):

- [`docs/architecture/mcp-implementation.md`](docs/architecture/mcp-implementation.md) — what Phase 2 delivers
- [`docs/setup/mcp.md`](docs/setup/mcp.md) — running the MCP server

Phase 3 (corpus + retrieval):

- [`docs/architecture/corpus.md`](docs/architecture/corpus.md) — corpus roots and security boundary
- [`docs/architecture/document-pipeline.md`](docs/architecture/document-pipeline.md) — parsers, normalization, chunking
- [`docs/architecture/retrieval.md`](docs/architecture/retrieval.md) — indexing, lexical retrieval, evidence
- [`docs/setup/corpus.md`](docs/setup/corpus.md) — configuring a local corpus

Phase 4 (semantic/hybrid retrieval + memory):

- [`docs/architecture/semantic-retrieval.md`](docs/architecture/semantic-retrieval.md) — embedding provider, vector index
- [`docs/architecture/hybrid-retrieval.md`](docs/architecture/hybrid-retrieval.md) — fusion, diversity, reranker
- [`docs/architecture/memory.md`](docs/architecture/memory.md) — structured persistent memory
- [`docs/setup/semantic-retrieval.md`](docs/setup/semantic-retrieval.md) — enabling hybrid search + memory

Phase 5 (evidence integrity + verification):

- [`docs/architecture/evidence-integrity.md`](docs/architecture/evidence-integrity.md) — the evidence-integrity foundation
- [`docs/architecture/claims.md`](docs/architecture/claims.md) — claim model and lifecycle
- [`docs/architecture/verification.md`](docs/architecture/verification.md) — verification engine, rules, statuses, coverage
- [`docs/architecture/contradictions.md`](docs/architecture/contradictions.md) — contradiction types and detection
- [`docs/setup/verification.md`](docs/setup/verification.md) — enabling verification tools

Phase 6 (deterministic computation):

- [`docs/architecture/computation.md`](docs/architecture/computation.md) — the computation layer
- [`docs/architecture/duckdb.md`](docs/architecture/duckdb.md) — DuckDB analytics engine and SQL safety
- [`docs/architecture/python-sandbox.md`](docs/architecture/python-sandbox.md) — controlled Python sandbox
- [`docs/architecture/computation-provenance.md`](docs/architecture/computation-provenance.md) — provenance and freshness
- [`docs/setup/computation.md`](docs/setup/computation.md) — enabling computation tools

Phase 7 (research orchestration):

- [`docs/architecture/orchestration.md`](docs/architecture/orchestration.md) — the orchestration layer
- [`docs/architecture/planning.md`](docs/architecture/planning.md) — deterministic planning/classification
- [`docs/architecture/workflows.md`](docs/architecture/workflows.md) — workflow engine and stage executors
- [`docs/architecture/research-state-machine.md`](docs/architecture/research-state-machine.md) — state ownership and lifecycle
- [`docs/setup/research-workflows.md`](docs/setup/research-workflows.md) — enabling workflow tools

Phase 8 (inference runtime + Qwen):

- [`docs/architecture/inference-runtime.md`](docs/architecture/inference-runtime.md) — provider-neutral Inference Runtime
- [`docs/architecture/providers.md`](docs/architecture/providers.md) — provider abstraction & configuration
- [`docs/architecture/qwen-provider.md`](docs/architecture/qwen-provider.md) — Qwen backend adapter (model-specific capability discovery, `thinking_budget`, schema validation)
- [`docs/setup/inference.md`](docs/setup/inference.md) — enabling inference

Phase 9 (controlled tool loop + hybrid boundary):

- [`docs/architecture/tool-loop.md`](docs/architecture/tool-loop.md) — controlled model ↔ tool-call loop
- [`docs/architecture/inference-continuation.md`](docs/architecture/inference-continuation.md) — continuation & preserved reasoning state
- [`docs/architecture/hybrid-mode.md`](docs/architecture/hybrid-mode.md) — hybrid Studio/Gateway boundary contract
- [`docs/setup/gateway-inference.md`](docs/setup/gateway-inference.md) — enabling gateway inference

Full architecture docs:

| Area | Document |
|------|----------|
| System overview | [`system-overview.md`](docs/architecture/system-overview.md) |
| Runtime boundaries | [`runtime-boundaries.md`](docs/architecture/runtime-boundaries.md) |
| Execution model | [`execution-model.md`](docs/architecture/execution-model.md) |
| Domain contracts | [`domain-contracts.md`](docs/architecture/domain-contracts.md) |
| Operating modes / inference ownership | [`operating-modes.md`](docs/architecture/operating-modes.md) |
| Capability negotiation | [`capability-negotiation.md`](docs/architecture/capability-negotiation.md) |
| Component boundaries | [`component-boundaries.md`](docs/architecture/component-boundaries.md) |
| Polyglot (language) boundaries | [`polyglot-boundaries.md`](docs/architecture/polyglot-boundaries.md) |
| Data flow | [`data-flow.md`](docs/architecture/data-flow.md) |
| Reasoning engine | [`reasoning-engine.md`](docs/architecture/reasoning-engine.md) |
| MCP | [`mcp.md`](docs/architecture/mcp.md) |
| Retrieval | [`retrieval.md`](docs/architecture/retrieval.md) |
| Memory | [`memory.md`](docs/architecture/memory.md) |
| Inference abstraction | [`inference.md`](docs/architecture/inference.md) |
| Security | [`security.md`](docs/architecture/security.md) |
| Architecture review | [`architecture-review.md`](docs/architecture/architecture-review.md) |
| Implementation roadmap | [`implementation-phases.md`](docs/architecture/implementation-phases.md) |
| Phase 1 contracts | [`phase-1-contracts.md`](docs/architecture/phase-1-contracts.md) |
| Domain model | [`domain-model.md`](docs/architecture/domain-model.md) |
| Runtime contracts | [`runtime-contracts.md`](docs/architecture/runtime-contracts.md) |
| MCP implementation | [`mcp-implementation.md`](docs/architecture/mcp-implementation.md) |
| MCP setup | [`setup/mcp.md`](docs/setup/mcp.md) |
| Corpus | [`corpus.md`](docs/architecture/corpus.md) |
| Document pipeline | [`document-pipeline.md`](docs/architecture/document-pipeline.md) |
| Retrieval | [`retrieval.md`](docs/architecture/retrieval.md) |
| Semantic retrieval | [`semantic-retrieval.md`](docs/architecture/semantic-retrieval.md) |
| Hybrid retrieval | [`hybrid-retrieval.md`](docs/architecture/hybrid-retrieval.md) |
| Memory | [`memory.md`](docs/architecture/memory.md) |
| Evidence integrity | [`evidence-integrity.md`](docs/architecture/evidence-integrity.md) |
| Claims | [`claims.md`](docs/architecture/claims.md) |
| Verification | [`verification.md`](docs/architecture/verification.md) |
| Contradictions | [`contradictions.md`](docs/architecture/contradictions.md) |
| Computation | [`computation.md`](docs/architecture/computation.md) |
| DuckDB | [`duckdb.md`](docs/architecture/duckdb.md) |
| Python sandbox | [`python-sandbox.md`](docs/architecture/python-sandbox.md) |
| Computation provenance | [`computation-provenance.md`](docs/architecture/computation-provenance.md) |
| Orchestration | [`orchestration.md`](docs/architecture/orchestration.md) |
| Planning | [`planning.md`](docs/architecture/planning.md) |
| Workflows | [`workflows.md`](docs/architecture/workflows.md) |
| Research state machine | [`research-state-machine.md`](docs/architecture/research-state-machine.md) |
| Inference runtime | [`inference-runtime.md`](docs/architecture/inference-runtime.md) |
| Providers | [`providers.md`](docs/architecture/providers.md) |
| Qwen provider | [`qwen-provider.md`](docs/architecture/qwen-provider.md) |
| Corpus setup | [`setup/corpus.md`](docs/setup/corpus.md) |
| Semantic setup | [`setup/semantic-retrieval.md`](docs/setup/semantic-retrieval.md) |
| Verification setup | [`setup/verification.md`](docs/setup/verification.md) |
| Computation setup | [`setup/computation.md`](docs/setup/computation.md) |
| Workflow setup | [`setup/research-workflows.md`](docs/setup/research-workflows.md) |
| Inference setup | [`setup/inference.md`](docs/setup/inference.md) |
| Decisions (ADRs) | [`decisions/`](docs/architecture/decisions/) |
| Mermaid diagrams | [`diagrams/`](docs/architecture/diagrams/) |

## Status

Phase 0.75 (architecture) is the approved baseline. Phases 1, 1.1, 1.2 (core
contracts + hardening), Phase 2 (MCP server), Phase 3 (local corpus + lexical
retrieval), Phase 4 (semantic + hybrid retrieval and persistent memory),
Phase 5 (evidence integrity and verification foundation), Phase 6
(deterministic computation and sandboxed analysis), Phase 7 (research
orchestration and workflow execution), Phase 8 (provider-neutral inference
runtime + Qwen backend), Phase 8.1 (model-specific Qwen capability discovery,
`thinking_budget`, full tool schemas, structured-output schema validation, and
stream-idle semantics), Phase 8.2 (per-model `preserve_thinking` /
structured-output / tool-calling / streaming and `qwen3.7-max` pinned to
official docs), Phase 8.3 (contextual model availability — endpoint /
region / plan / inference mode — with `qwen3.8-max-preview` represented as an
official Token-Plan preview and distinct availability errors), Phase 8.4
(endpoint-profile-driven HTTP endpoint, transient `reasoning_content` for
multi-turn continuation, and `qwen3.8-max-preview` context corrected to
983,616), Phase 9 (controlled model ↔ tool-call loop with authorization,
schema validation, continuation, loop budgets, repeated-call guards, and the
hybrid Studio/Gateway boundary contract), and Phase 9.1 (tool-loop continuation
semantics and malformed-tool-argument rejection) are **complete**.
The Research Runtime remains
provider- and transport-independent; the MCP server is a thin adapter over it,
now serving hybrid evidence, project-scoped memory, deterministic claim
verification, bounded computation, deterministic research workflows, and a
single-invocation inference flow (credentials never exposed to MCP). See
[`implementation-phases.md`](docs/architecture/implementation-phases.md).

### Develop

```text
pip install -e ".[dev]"
pytest            # unit + contract + vertical-slice + MCP integration tests
ruff check .      # lint
mypy              # type check
```
