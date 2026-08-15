"""The deterministic workflow engine.

Executes a persisted :class:`ResearchPlan` as a resumable :class:`WorkflowRun`
through registered :class:`StageExecutor` implementations. It enforces
guardrails (stage/round limits), explicit retry policies, idempotent stage
re-entry, and loop back-edges for evidence gaps and contradictions — always
bounded, never invoking a model.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from qwen_research.domain.errors import (
    PlanNotFoundError,
    ResearchTaskNotFoundError,
    RunNotFoundError,
    UnsupportedOperationError,
)
from qwen_research.orchestration.models import (
    EventType,
    ResearchPlan,
    ResearchStage,
    ResearchTask,
    RunStatus,
    StageResult,
    StageStatus,
    StageType,
    WorkflowEvent,
    WorkflowGuardrails,
    WorkflowRun,
    as_str_tuple,
    is_terminal_run_status,
)
from qwen_research.orchestration.stages import StageExecutionContext, StageExecutor, StageRuntime
from qwen_research.orchestration.store import OrchestrationStore

#: Loop control → (counter key, guardrail limit, target stage id).
_LOOP_TARGETS: dict[str, tuple[str, str, str]] = {
    "retrieve": ("evidence_rounds", "max_retrieval_rounds", "retrieve"),
    "compute": ("computation_rounds", "max_computation_rounds", "compute"),
}

#: Terminal stage statuses that satisfy dependencies.
_DONE_STAGE: frozenset[StageStatus] = frozenset({StageStatus.COMPLETED, StageStatus.SKIPPED})


class WorkflowEngine:
    """Provider-independent deterministic workflow executor."""

    def __init__(
        self,
        store: OrchestrationStore,
        *,
        runtime: StageRuntime | None = None,
        guardrails: WorkflowGuardrails | None = None,
        executors: dict[StageType, StageExecutor] | None = None,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._guardrails = guardrails or WorkflowGuardrails()
        from qwen_research.orchestration.stages import executor_registry

        self._executors = dict(executors or executor_registry())

    # -- lifecycle ---------------------------------------------------------

    def create_run(
        self, task: ResearchTask, plan: ResearchPlan, *, workflow_id: str | None = None
    ) -> WorkflowRun:
        run = WorkflowRun.create(task.task_id, plan, workflow_id or plan.plan_id)
        self._store.save_run(run)
        self._record(run.run_id, EventType.CREATED, "created")
        return run

    def start(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status is not RunStatus.CREATED:
            return run
        run = dataclasses.replace(
            run,
            status=RunStatus.RUNNING,
            started_at=run.started_at or _now(),
            updated_at=_now(),
        )
        self._store.save_run(run)
        self._record(run_id, EventType.STARTED, "running")
        return run

    def step(self, run_id: str) -> tuple[WorkflowRun, dict[str, str]]:
        run = self._require_run(run_id)
        if run.status is RunStatus.CREATED:
            run = self.start(run_id)
        if run.status is RunStatus.PAUSED or is_terminal_run_status(run.status):
            return run, {}

        stage = self._next_ready(run)
        if stage is None:
            return run, {}

        run = dataclasses.replace(
            run,
            current_stage=stage.stage_id,
            stages=_replace_stage(run.stages, stage.stage_id, status=StageStatus.RUNNING),
            updated_at=_now(),
        )
        self._store.save_run(run)

        executor = self._executors.get(stage.type)
        if executor is None:
            return (
                self._fail_stage(run, stage, f"no executor for stage type {stage.type.value!r}"),
                {},
            )

        context = StageExecutionContext(
            task=self._require_task(run.task_id),
            plan=self._require_plan(run.plan_id),
            run=run,
            project_id=self._task(run.task_id).project_id,
            runtime=self._runtime or _NullRuntime(),
            outputs=run.outputs,
            guardrails=self._guardrails,
        )
        try:
            result = executor.execute(context)
        except UnsupportedOperationError as exc:
            return self._block(run, stage, str(exc)), {}
        except Exception as exc:  # noqa: BLE001 — normalize any stage failure
            return self._handle_failure(run, stage, exc), {}

        return self._commit_result(run, stage, result)

    def execute_until_blocked(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status is RunStatus.CREATED:
            run = self.start(run_id)
        steps = 0
        while steps < self._guardrails.max_stages:
            steps += 1
            run, control = self.step(run_id)
            if is_terminal_run_status(run.status) or run.status is RunStatus.PAUSED:
                break
            if not control:
                # No ready stage left and no loop requested → settle.
                if self._next_ready(run) is None:
                    run = self._settle(run)
                    break
                continue
            run = self._apply_loop(run, control)
            if is_terminal_run_status(run.status):
                break
        else:
            run = self._block(run, None, "max_stages guardrail exceeded")
        self._store.save_run(run)
        return run

    def pause(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status in (RunStatus.RUNNING, RunStatus.WAITING):
            run = dataclasses.replace(run, status=RunStatus.PAUSED, updated_at=_now())
            self._store.save_run(run)
            self._record(run_id, EventType.PAUSED, "paused")
        return run

    def resume(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if run.status is RunStatus.PAUSED:
            run = dataclasses.replace(run, status=RunStatus.RUNNING, updated_at=_now())
            self._store.save_run(run)
            self._record(run_id, EventType.RESUMED, "running")
        return run

    def cancel(self, run_id: str) -> WorkflowRun:
        run = self._require_run(run_id)
        if not is_terminal_run_status(run.status):
            run = dataclasses.replace(
                run, status=RunStatus.CANCELLED, completed_at=_now(), updated_at=_now()
            )
            self._store.save_run(run)
            self._record(run_id, EventType.CANCELLED, "cancelled")
        return run

    def get_run(self, run_id: str) -> WorkflowRun:
        return self._require_run(run_id)

    def get_events(self, run_id: str) -> list[WorkflowEvent]:
        return self._store.get_events(run_id)

    # -- internals ---------------------------------------------------------

    def _commit_result(
        self, run: WorkflowRun, stage: ResearchStage, result: StageResult
    ) -> tuple[WorkflowRun, dict[str, str]]:
        status = result.status
        if result.status is StageStatus.FAILED:
            status = StageStatus.FAILED
        outputs = dict(run.outputs)
        outputs.update(result.outputs)
        accounting = dict(run.accounting)
        accounting = _bump_accounting(accounting, stage.type, result)
        run = dataclasses.replace(
            run,
            stages=_replace_stage(run.stages, stage.stage_id, status=status),
            outputs=outputs,
            accounting=accounting,
            degradation=tuple(dict.fromkeys(run.degradation + result.degradation)),
            warnings=tuple(dict.fromkeys(run.warnings + result.warnings)),
            updated_at=_now(),
        )
        self._store.save_run(run)
        self._record(
            run.run_id,
            EventType.COMPLETED if status in _DONE_STAGE else EventType.FAILED,
            status.value,
            stage_id=stage.stage_id,
            references=result.references,
        )
        return run, dict(result.control)

    def _handle_failure(
        self, run: WorkflowRun, stage: ResearchStage, exc: Exception
    ) -> WorkflowRun:
        name = type(exc).__name__
        if (
            name in stage.retry_policy.retryable_errors
            and stage.attempts < stage.retry_policy.max_attempts
        ):
            if stage.retry_policy.backoff_seconds:
                time.sleep(stage.retry_policy.backoff_seconds)
            run = dataclasses.replace(
                run,
                stages=_replace_stage(
                    run.stages,
                    stage.stage_id,
                    status=StageStatus.PENDING,
                    attempts=stage.attempts + 1,
                ),
                updated_at=_now(),
            )
            self._store.save_run(run)
            self._record(run.run_id, EventType.RETRIED, "retried", stage_id=stage.stage_id)
            return run
        # Non-retryable → fail the stage and the run.
        run = self._fail_stage(run, stage, f"{name}: {exc}")
        return dataclasses.replace(
            run, status=RunStatus.FAILED, errors=run.errors + (f"{name}: {exc}",),
            completed_at=_now(),
        )

    def _fail_stage(self, run: WorkflowRun, stage: ResearchStage, reason: str) -> WorkflowRun:
        run = dataclasses.replace(
            run,
            stages=_replace_stage(run.stages, stage.stage_id, status=StageStatus.FAILED),
            errors=run.errors + (reason,),
            updated_at=_now(),
        )
        self._store.save_run(run)
        self._record(run.run_id, EventType.FAILED, "failed", stage_id=stage.stage_id)
        return run

    def _block(
        self, run: WorkflowRun, stage: ResearchStage | None, reason: str
    ) -> WorkflowRun:
        run = dataclasses.replace(
            run,
            status=RunStatus.BLOCKED,
            errors=run.errors + (reason,),
            completed_at=_now(),
            updated_at=_now(),
        )
        self._store.save_run(run)
        self._record(
            run.run_id,
            EventType.BLOCKED,
            "blocked",
            stage_id=stage.stage_id if stage else None,
        )
        return run

    def _apply_loop(self, run: WorkflowRun, control: dict[str, str]) -> WorkflowRun:
        kind = control.get("loop", "")
        target = _LOOP_TARGETS.get(kind)
        if target is None:
            return run
        counter_key, limit_attr, stage_id = target
        counters = dict(run.counters)
        limit = int(getattr(self._guardrails, limit_attr))
        if counters.get(counter_key, 0) >= limit:
            return self._block(run, None, f"{limit_attr} guardrail exceeded ({kind} loop)")
        counters[counter_key] = counters.get(counter_key, 0) + 1
        stages = _reset_from(run.stages, stage_id)
        run = dataclasses.replace(run, stages=stages, counters=counters, updated_at=_now())
        self._store.save_run(run)
        self._record(run.run_id, EventType.RETRIED, f"loop:{kind}", stage_id=stage_id)
        return run

    def _settle(self, run: WorkflowRun) -> WorkflowRun:
        if is_terminal_run_status(run.status):
            return run
        status = self._evaluate_completion(run)
        run = dataclasses.replace(
            run, status=status, completed_at=_now(), updated_at=_now()
        )
        event_type = (
            EventType.COMPLETED
            if status in (RunStatus.READY_FOR_SYNTHESIS, RunStatus.SYNTHESIS_REQUIRED)
            else EventType.BLOCKED
        )
        self._record(run.run_id, event_type, status.value)
        return run

    def _evaluate_completion(self, run: WorkflowRun) -> RunStatus:
        """Decide the terminal state.

        A model-free workflow is **never** answer-complete: it ends at
        ``READY_FOR_SYNTHESIS`` (clean) or ``SYNTHESIS_REQUIRED`` (degraded) —
        never ``COMPLETED``. Missing required capabilities are surfaced as
        ``SYNTHESIS_REQUIRED`` with explicit degradation; unmet completion
        criteria are ``PARTIAL``.
        """
        plan = self._require_plan(run.plan_id)
        criteria = plan.completion_criteria
        outputs = run.outputs
        evidence = len(as_str_tuple(outputs.get("evidence")))
        sources = outputs.get("evidence_sources", ())
        diversity = len(set(sources)) if isinstance(sources, (list, tuple)) else 0
        # Missing required capabilities → explicit degraded synthesis state.
        if run.degradation:
            return RunStatus.SYNTHESIS_REQUIRED
        if criteria.min_evidence_count and evidence < criteria.min_evidence_count:
            return RunStatus.PARTIAL
        if criteria.min_source_diversity and diversity < criteria.min_source_diversity:
            return RunStatus.PARTIAL
        if criteria.verification_completed and not outputs.get("verification_reports"):
            return RunStatus.PARTIAL
        if criteria.dataset_profiled and not outputs.get("dataset_profile"):
            return RunStatus.PARTIAL
        if criteria.analysis_completed and not outputs.get("computations"):
            return RunStatus.PARTIAL
        if criteria.result_persisted and not (
            outputs.get("computations") or outputs.get("memory_ids")
        ):
            return RunStatus.PARTIAL
        if criteria.provenance_recorded and not outputs.get("memory_ids"):
            return RunStatus.PARTIAL
        if criteria.critical_contradictions_resolved and as_str_tuple(
            outputs.get("contradictions")
        ):
            return RunStatus.PARTIAL
        return RunStatus.READY_FOR_SYNTHESIS

    def _next_ready(self, run: WorkflowRun) -> ResearchStage | None:
        statuses = {s.stage_id: s.status for s in run.stages}
        for stage in run.stages:
            if stage.status is not StageStatus.PENDING:
                continue
            if all(statuses.get(d) in _DONE_STAGE for d in stage.dependencies):
                return stage
        return None

    # -- store helpers -----------------------------------------------------

    def _require_run(self, run_id: str) -> WorkflowRun:
        run = self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"run {run_id!r} not found")
        return run

    def _require_plan(self, plan_id: str) -> ResearchPlan:
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(f"plan {plan_id!r} not found")
        return plan

    def _require_task(self, task_id: Any) -> ResearchTask:
        task = self._store.get_task(task_id)
        if task is None:
            raise ResearchTaskNotFoundError(f"research task {task_id!r} not found")
        return task

    def _task(self, task_id: Any) -> ResearchTask:
        return self._require_task(task_id)

    def _record(
        self,
        run_id: str,
        event_type: EventType,
        status: str,
        *,
        stage_id: str | None = None,
        references: tuple[str, ...] = (),
    ) -> None:
        self._store.save_event(
            WorkflowEvent.create(
                run_id, event_type, status, stage_id=stage_id, references=references
            )
        )


class _NullRuntime:
    """A runtime stub so a run can be inspected without any wired capabilities."""

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        def _missing(*args: object, **kwargs: object) -> None:
            raise UnsupportedOperationError(f"no runtime capability {name!r} configured")

        return _missing


def _now() -> Any:
    from qwen_research.common.timestamps import utc_now

    return utc_now()


def _replace_stage(
    stages: tuple[ResearchStage, ...],
    stage_id: str,
    *,
    status: StageStatus | None = None,
    attempts: int | None = None,
) -> tuple[ResearchStage, ...]:
    out: list[ResearchStage] = []
    for stage in stages:
        if stage.stage_id == stage_id:
            out.append(
                dataclasses.replace(
                    stage,
                    status=status if status is not None else stage.status,
                    attempts=attempts if attempts is not None else stage.attempts,
                )
            )
        else:
            out.append(stage)
    return tuple(out)


def _reset_from(stages: tuple[ResearchStage, ...], target_id: str) -> tuple[ResearchStage, ...]:
    """Reset the loop target stage and every later stage to PENDING."""
    out: list[ResearchStage] = []
    resetting = False
    for stage in stages:
        if stage.stage_id == target_id:
            resetting = True
        if resetting:
            out.append(dataclasses.replace(stage, status=StageStatus.PENDING, attempts=0))
        else:
            out.append(stage)
    return tuple(out)


def _bump_accounting(
    accounting: dict[str, int], stage_type: StageType, result: StageResult
) -> dict[str, int]:
    """Accumulate resource-accounting counters from a stage's metrics.

    Executors report the exact invocation counts (e.g. ``verification_calls``
    is the number of claims verified), so the engine simply sums integer
    metrics — it does not fabricate a per-stage count.
    """
    del stage_type  # accounting is driven by executor-reported metrics
    out = dict(accounting)
    for metric_key, value in result.metrics.items():
        if isinstance(value, int):
            out[metric_key] = out.get(metric_key, 0) + value
    return out
