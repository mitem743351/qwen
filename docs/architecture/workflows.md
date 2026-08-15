# Workflow Engine & Stage Executors

The workflow engine executes a persisted `ResearchPlan` as a resumable
`WorkflowRun` through registered `StageExecutor` implementations.

Module: `python/qwen_research/orchestration/engine.py` + `stages.py`.

---

## Workflow engine

```text
WorkflowEngine
    create_run() · start() · pause() · resume() · cancel()
    step() · execute_until_blocked() · get_state() · get_events()
```

The engine works from **persistent state** (no background/distributed task
system). `step()` executes exactly one ready stage; `execute_until_blocked()`
loops until the run reaches a terminal state, a loop guardrail, or a blocking
capability gap.

### Ready-stage selection

A stage is ready when its status is `PENDING` and every dependency is
`COMPLETED` or `SKIPPED`. Stages are executed in plan order (topological).

### Stage execution contract

```text
StageExecutor.supports(stage_type) → bool
StageExecutor.execute(context) → StageResult(status, outputs, references,
                                             metrics, warnings, degradation, control)
```

An executor must not modify unrelated subsystems; it returns a `StageResult`
which the engine merges into the run.

## Stage executors (built-in)

| Stage | Integrates via |
|-------|----------------|
| `CLASSIFY` / `PLAN` | classification/plan already produced (no-op) |
| `RETRIEVE` | `runtime.search_corpus` (lexical/hybrid by profile) — chunks are **candidates**, not evidence of support |
| `CLAIM` | `runtime.create_claim` (FACT_CHECK sub-questions) |
| `ASSESS_EVIDENCE` | records **neutral `candidate_evidence`**; never creates claim→evidence links |
| `VERIFY` | `runtime.verify_claim`; signals structural contradiction loops |
| `CONTRADICTIONS` | `runtime.get_contradictions` |
| `CORROBORATE` | Phase-5 `SourceIndependence` (`count_independent_sources`) |
| `DESCRIBE_DATASET` | `runtime.describe_dataset` |
| `COMPUTE` | `runtime.run_analysis` (from plan `ComputationSpec`) |
| `MEMORY` | `runtime.save_research_memory` (idempotent) |
| `SYNTHESIZE` | `runtime.build_research_context` → `SynthesisDraft` + `SynthesisRequest` |
| `FINALIZE` | marks the deterministic workflow complete |

No executor constructs DuckDB SQL, duplicates verification rules, or writes raw
SQL. **Assessment and corroboration are deterministic and model-free** — no
executor manufactures a claim→evidence `SUPPORTS` relationship from retrieval.

## Retry policy

`RetryPolicy(max_attempts, retryable_errors, backoff)` retries **only** known
transient failures (e.g. `RetrievalBackendUnavailable`). Validation, permission,
security, and unsupported-capability failures are never retried.

## Idempotency

Stages have stable ids and statuses; re-running a run only executes `PENDING`
stages. Claim/memory executors check prior outputs before re-creating, so a
restart does not duplicate claims, memory entries, verification reports, or
artifacts.

## Loops (bounded)

- **Contradiction** — `VERIFY` reports a `CONFIRMED` contradiction (structural)
  → loop back to `RETRIEVE` (bounded by `max_verification_rounds`).
- **Computation gap** — a claim requires calculation → `COMPUTE` (bounded by `max_computation_rounds`).

`INSUFFICIENT_EVIDENCE` is **not** looped in a model-free system: re-retrieving
cannot manufacture support, so it is surfaced as a warning and left for the
future synthesis step. Loops reset the target stage and its dependents to
`PENDING`; exceeding a guardrail marks the run `BLOCKED`.

## Resource accounting

The engine accumulates `retrieval_calls · verification_calls ·
computation_calls · memory_reads · memory_writes · artifacts_created` from
executor-reported metrics — groundwork for future XHIGH scheduling.

## Observability

`get_run` / `get_events` / `get_plan` expose every stage transition and event
(`CREATED · STARTED · COMPLETED · FAILED · RETRIED · PAUSED · RESUMED ·
BLOCKED · CANCELLED`). No hidden chain-of-thought is ever logged.
