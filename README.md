# Qwen Research System

A **local, single-user-first AI research infrastructure** that extends
**Qwen Studio** (via MCP) into a powerful API/agent runtime: configurable
deep-reasoning workflows, long-output generation, a private local corpus,
persistent research memory, verification/citation/provenance, and deterministic
computation — while Qwen Studio keeps its native conversational and web-search
capabilities.

> **Current status: Phase 0.75 — Architecture.** This repository currently
> contains **architecture documentation only**. No runtime code, servers, or
> databases exist yet.

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
| Decisions (ADRs) | [`decisions/`](docs/architecture/decisions/) |
| Mermaid diagrams | [`diagrams/`](docs/architecture/diagrams/) |

## Status

Phase 0.75 is complete when the architecture is **internally consistent** —
including inference ownership (`STUDIO_NATIVE` / `GATEWAY_INFERENCE` /
`HYBRID`) and the runtime boundaries (MCP Server / Research Runtime /
Inference Runtime) — and ready to serve as a stable contract for later
implementation prompts. Phase 1 (core domain/runtime contracts) must not begin
until then — see [`implementation-phases.md`](docs/architecture/implementation-phases.md).
