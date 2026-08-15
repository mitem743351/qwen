# Research Orchestration

Phase 7 turns the repository's individual capabilities (retrieval, memory,
verification, computation, MCP) into a **coherent, deterministic research
orchestration system**. The Research Runtime becomes the orchestrator of
capabilities without becoming a monolithic implementation.

> **Objective:** given a research task, construct and execute a bounded,
> resumable, auditable workflow that decides what information/computation is
> required, gathers evidence, verifies it, updates research state, and produces
> a structured synthesis input for a future inference runtime.
>
> **No model invocation in Phase 7** — no Qwen API, no gateway inference, no
> XHIGH model inference.

Module: `python/qwen_research/orchestration/`.

---

## Execution model

```text
User Request → Research Runtime → Task Classification → Research Planning
  → Workflow Execution (Retrieval / Memory / Evidence / Verification / Computation)
  → Evidence/Verification/Computation Summary → Synthesis Context
  → [future Inference Runtime]
```

The final step is an **inference request boundary** (`SynthesisRequest`), not a
model call.

---

## Separation of concerns

```text
Planner          = decides what should happen (deterministic rules)
Workflow Engine  = controls execution order (stage DAG + guardrails)
Research Runtime = application boundary
Retrieval        = finds evidence
Verification     = evaluates evidence integrity
Computation      = performs deterministic analysis
Memory           = stores persistent structured research state
Inference Runtime = future model execution boundary (not implemented)
```

Provider-specific inference logic never enters the planner or workflow engine.

---

## Core objects

| Object | Responsibility |
|--------|----------------|
| `ResearchTask` | task metadata (type, complexity, profile, plan/workflow refs) |
| `ResearchPlan` | intended workflow: stages, requirements, completion criteria, budget |
| `WorkflowRun` | execution state: stage statuses, outputs, counters, accounting |
| `WorkflowEvent` | structured audit trail (no hidden reasoning) |
| `ResearchStatus` | compact observability view (progress, degradation, blocking issues) |
| `SynthesisRequest` | provider-neutral future-inference bridge |

---

## Execution lifecycle

```text
plan_research → ResearchTask + ResearchPlan (persisted)
start_research → WorkflowRun (execute_until_blocked, synchronous)
pause / resume / cancel → engine-level state transitions
```

Execution is **synchronous** (no background distributed worker). `pause` /
`resume` / `cancel` operate on persisted run state and are exercised at the
engine level; `start_research` runs to completion or to a blocking state.

---

## Guardrails (orchestration budgets, not model-token budgets)

`max_stages · max_retries · max_retrieval_rounds · max_verification_rounds ·
max_computation_rounds · max_time · max_tool_calls`.

Evidence-gap, contradiction, and computation loops are bounded by these
counters; a loop that exceeds its budget marks the run `BLOCKED`, never an
infinite loop and never a fabricated completion.

---

## Failure semantics

`COMPLETED · PARTIAL · BLOCKED · FAILED · CANCELLED · PAUSED · WAITING`. A
failure is never an empty result and never silently converted to success:
retrieval degradation → `PARTIAL`; a missing capability → `BLOCKED`; a
non-retryable stage failure → `FAILED`.

See [`planning.md`](planning.md), [`workflows.md`](workflows.md),
[`research-state-machine.md`](research-state-machine.md), and
[`../setup/research-workflows.md`](../setup/research-workflows.md).
