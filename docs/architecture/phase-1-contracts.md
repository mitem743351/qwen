# Phase 1 — Core Domain and Runtime Contracts

> **Status:** implemented (contracts only). No MCP, Qwen, retrieval, database,
> or dashboard implementation exists.

Phase 1 establishes the **minimum executable foundation**: stable domain
objects, runtime interfaces, a state model, an error model, a configuration
model, and testable in-memory contracts. It does **not** build the research
system.

This document distinguishes **implemented contracts** (present in
`python/qwen_research/`) from **future implementations** (deferred phases).

---

## What Phase 1 delivers

| Concern | Implemented contract | Future implementation |
|---------|---------------------|----------------------|
| Domain objects | `python/qwen_research/domain/` | — |
| Reasoning profiles/budgets | `domain/reasoning.py` (FAST…EXTREME + `ReasoningBudget`) | adaptive scheduling |
| Inference contracts | `domain/inference.py`, `inference/interfaces.py` | `QwenProvider`, local Qwen, network |
| Capability negotiation | `negotiate()` → `APPLY`/`DEGRADE`/`EMULATE`/`REJECT` | provider adapters (Phase 8) |
| MCP contracts | `research/interfaces.py` (`MCPRequest`/`MCPResult`) | MCP wire protocol (Phase 2) |
| Tool abstraction | `tools/` (`Tool`, `ToolRegistry`) | MCP/CLI/API adapters |
| Workflow contracts | `workflows/` (`Workflow`, registries) | deep-research workflows |
| Research Runtime | `research/` (`ResearchRuntime` protocol + in-memory impl) | retrieval/verification wiring |
| State machine | `domain/task.py` (14 states + validation) | persistence |
| Error model | `domain/errors.py` | — |
| Serialization | `common/serialization.py` | database format |
| Configuration model | `config.py` | env/file loading |
| Persistence | `persistence/interfaces.py` (protocols) | SQLite/PostgreSQL/DuckDB |
| In-memory stores | `research/state.py` | — |

---

## Layering (dependency rule)

```text
domain  ──▶ application/runtime (research, tools, workflows, inference, persistence)
                └──▶ adapters (MCP, CLI, API)   [future]
```

Never: `domain → MCP`, `domain → Qwen API`, `workflow → HTTP`.

---

## What is explicitly NOT implemented

- MCP server / protocol
- Qwen API / any inference provider
- retrieval / corpus / document parsing
- real persistence (no SQLite/PostgreSQL/DuckDB)
- verification engine / computation engine
- dashboard, Rust runtime, TypeScript

Operations that depend on these (e.g. `retrieve_context`, `verify_claim`) raise
`UnsupportedOperationError` rather than returning fabricated results.

---

## Running the checks

```text
pip install -e ".[dev]"
pytest            # 58 tests
ruff check .      # lint
mypy              # type check
```

See [`domain-model.md`](domain-model.md) and [`runtime-contracts.md`](runtime-contracts.md).
