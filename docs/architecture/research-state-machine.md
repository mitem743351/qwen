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
CREATED → RUNNING → { READY_FOR_SYNTHESIS | SYNTHESIS_REQUIRED | PARTIAL
                      | BLOCKED | FAILED | CANCELLED }
              ↓ PAUSE → PAUSED → RESUME → RUNNING
```

`BLOCKED`, `FAILED`, `CANCELLED`, `PARTIAL`, `SYNTHESIS_REQUIRED`, and
`READY_FOR_SYNTHESIS` are terminal; `PAUSED`/`WAITING` are control states.

### Workflow-complete ≠ answer-complete

A **model-free** workflow can only ever be *workflow-complete*: it has gathered,
assessed, verified, and computed everything it deterministically can. It can
never be *answer-complete* — producing an answer requires synthesis by a model.
Therefore the deterministic engine terminates at:

- `READY_FOR_SYNTHESIS` — all required stages ran, completion criteria met, no
  degradation; a `SynthesisRequest` is ready for the future inference runtime.
- `SYNTHESIS_REQUIRED` — the workflow reached its natural end but a **required
  capability was missing/degraded**, surfaced explicitly in `run.degradation`.

`COMPLETED` is the reserved *answer-complete* terminal for the future inference
phase and is **never** produced by the deterministic engine.

### Source diversity in completion

A `min_source_diversity` requirement is evaluated against the Phase-5
`SourceIndependence` subsystem (`count_independent_sources`), not a raw
document count. `document_count` (distinct documents) and
`independent_source_count` (independent source identities) are distinct: only
the latter satisfies an "independent sources" / "source diversity" /
"corroboration" requirement, and the two are both reported (for diagnostics)
via `ResearchStatus` and `get_research_summary`.

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
