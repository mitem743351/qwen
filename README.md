# Qwen Research System

A **local, single-user-first AI research infrastructure** that extends
**Qwen Studio** (via MCP) into a powerful API/agent runtime: configurable
deep-reasoning workflows, long-output generation, a private local corpus,
persistent research memory, verification/citation/provenance, and deterministic
computation — while Qwen Studio keeps its native conversational and web-search
capabilities.

> **Current status: Phase 0 — Architecture.** This repository currently
> contains **architecture documentation only**. No runtime code, servers, or
> databases exist yet.

## What this is

A clean, layered architecture with strict separation between:

- **Qwen Studio** (human interface)
- **MCP / Gateway** (protocol boundary)
- **Reasoning + Orchestration** (workflow and policy)
- **Knowledge / Computation / Tools** (capabilities)
- **Local Data** (storage and corpus)

…and between eight concerns: model capability, inference configuration,
reasoning workflow, tool execution, knowledge retrieval, persistent state,
verification, and deterministic computation. `XHIGH`/`EXTREME` reasoning is
modeled as an explicit **workflow/inference policy**, not a longer prompt, and
all model access goes through a provider-independent **inference abstraction**
so the system survives a Qwen backend change.

## Documentation

Start here:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the binding architecture contract
- [`SECURITY.md`](SECURITY.md) — security posture
- [`docs/architecture/system-overview.md`](docs/architecture/system-overview.md)

Full architecture docs:

| Area | Document |
|------|----------|
| System overview | [`system-overview.md`](docs/architecture/system-overview.md) |
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

Phase 0 is complete when the architecture is **internally consistent** and
ready to serve as a stable contract for later implementation prompts. Phase 1
(core skeleton) must not begin until then — see
[`implementation-phases.md`](docs/architecture/implementation-phases.md).
