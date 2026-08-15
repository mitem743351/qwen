# Trajectory Orchestration (Phase 10)

Bounded, distinct research trajectories for XHIGH/EXTREME.

`ResearchTrajectory` carries `trajectory_id`, `strategy`, `objective`,
`evidence_refs`, `claims`, `verification_refs`, `computation_refs`, `status`.

Strategies (`TrajectoryStrategy`): `DIRECT`, `COUNTERARGUMENT`, `LITERATURE`,
`DATA_DRIVEN`, `MECHANISTIC`. Different trajectories must differ in at least one
meaningful dimension — they are never clones of the same work.

---

## Budget

Trajectory count is bounded by `max_trajectory_count` (XHIGH 3, EXTREME 5). The
global ceiling is authoritative: a fifth trajectory when only four are allowed
is denied with `RESOURCE_LIMIT`/not-admitted, never silently created.

Each trajectory executes against the shared global budget via `run_trajectory`
(reserve/commit per dimension); a trajectory can never exceed the ceiling, and
its consumed budget is permanent within the run.

## Restart

A restarted trajectory resumes from persisted progress; consumed budget is
preserved (never reset). Trajectory recovery operates through the frozen
Phase-9 execution store — a crash-ambiguous side effect is `UNKNOWN`, never
silently duplicated.

## Aggregation

Trajectory results are **not** majority-voted natural-language answers. The
final synthesis compares structured `claims`, `evidence`, `verification`,
`contradictions`, `computation`, and `unresolved questions` across trajectories.

## Context isolation

Each trajectory owns its conversation state, tool-call history, and transient
reasoning state; hidden reasoning never leaks between trajectories.

See [`test-time-scaling.md`](test-time-scaling.md).
