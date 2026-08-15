# Research State Machine & Ownership

Phase 7 introduces clear ownership across task, plan, run, and accumulated
research knowledge — no conflicting sources of truth.

---

## Ownership

```text
Task            = user-level work unit (classification metadata)
ResearchPlan    = intended workflow (stages, requirements, criteria, budget)
WorkflowRun     = execution state (stage statuses, outputs, counters)
ResearchState   = accumulated research knowledge (claims, evidence, memory)
```

- The **domain `Task`** (Phase 1) remains the low-level work unit.
- **`ResearchTask`** (orchestration) adds type/complexity/profile/plan/run
  metadata and correlates by `task_id`.
- **`WorkflowRun`** is the resumable execution record (persisted in SQLite).
- **`ResearchState`** (Phase 1 domain) and the memory/verification/computation
  stores hold the *accumulated knowledge* the workflow produces.

## Run lifecycle

```text
CREATED → RUNNING → { COMPLETED | PARTIAL | BLOCKED | FAILED | CANCELLED }
              ↓ PAUSE → PAUSED → RESUME → RUNNING
```

`BLOCKED`, `FAILED`, `CANCELLED`, `PARTIAL`, and `COMPLETED` are terminal;
`PAUSED`/`WAITING` are control states.

## Stage lifecycle

```text
PENDING → RUNNING → { COMPLETED | SKIPPED | FAILED | BLOCKED }
```

`COMPLETED` and `SKIPPED` satisfy dependencies; `FAILED`/`BLOCKED` do not.

## Failure recovery

| Condition | Result |
|-----------|--------|
| retrieval backend unavailable | `BLOCKED` (or `PARTIAL` if it degraded with fallback) |
| verification unavailable | `BLOCKED` |
| computation timeout | `PARTIAL`/`FAILED` (computation result records the failure) |
| memory unavailable | `BLOCKED` |
| artifact failure | `FAILED` |

The workflow never fabricates a final result on failure.

## Provenance

Every workflow output remains traceable:

```text
task → stage → retrieval → evidence → verification → computation → memory
      → synthesis context
```

Only structured references are persisted — never hidden reasoning.

## State persistence

SQLite (`OrchestrationStore`, `schema_version=1`) persists research tasks,
plans, workflow runs, and events. Restart/resume re-loads a run and continues
from its last completed stage without duplicating claims, memory, verification
reports, or artifacts.
