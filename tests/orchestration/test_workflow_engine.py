"""Workflow engine unit tests: lifecycle, retry, failure, loops, idempotency."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qwen_research.domain.errors import RetrievalBackendUnavailable
from qwen_research.orchestration.engine import WorkflowEngine
from qwen_research.orchestration.models import (
    CompletionCriteria,
    EventType,
    PlanRequirements,
    ResearchPlan,
    ResearchStage,
    ResearchTask,
    RetryPolicy,
    RunStatus,
    StageResult,
    StageStatus,
    StageType,
    TaskComplexity,
    TaskType,
    WorkflowGuardrails,
)
from qwen_research.orchestration.stages import StageExecutionContext
from qwen_research.orchestration.store import OrchestrationStore


def _task(store: OrchestrationStore, project_id: str = "p") -> ResearchTask:
    task = ResearchTask.create(
        project_id, "task", TaskType.CUSTOM, TaskComplexity.SIMPLE, "FAST"
    )
    store.save_task(task)
    return task


def _plan(
    store: OrchestrationStore,
    task: ResearchTask,
    stages: tuple[ResearchStage, ...],
    criteria: CompletionCriteria | None = None,
) -> ResearchPlan:
    plan = ResearchPlan.create(
        task.task_id,
        task.description,
        stages,
        requirements=PlanRequirements(),
        completion_criteria=criteria or CompletionCriteria(min_source_diversity=0),
    )
    store.save_plan(plan, project_id=task.project_id)
    return plan


def _linear(stage_ids: tuple[str, ...]) -> tuple[ResearchStage, ...]:
    out: list[ResearchStage] = []
    prev: str | None = None
    for sid in stage_ids:
        out.append(
            ResearchStage(
                stage_id=sid, type=StageType.CUSTOM, name=sid, dependencies=(prev,) if prev else ()
            )
        )
        prev = sid
    return tuple(out)


class _NoopExecutor:
    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.CUSTOM

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed({"ran": True})


class _ConstExecutor:
    def __init__(self, stage_type: StageType, result: StageResult) -> None:
        self._type = stage_type
        self._result = result

    def supports(self, stage_type: StageType) -> bool:
        return stage_type is self._type

    def execute(self, context: StageExecutionContext) -> StageResult:
        return self._result


class _FailOnceExecutor:
    """Fails with a given exception on the first attempt, then succeeds."""

    def __init__(self, stage_type: StageType, exc_factory: Callable[[], Exception]) -> None:
        self._type = stage_type
        self._exc_factory = exc_factory
        self.calls = 0

    def supports(self, stage_type: StageType) -> bool:
        return stage_type is self._type

    def execute(self, context: StageExecutionContext) -> StageResult:
        self.calls += 1
        if self.calls == 1:
            raise self._exc_factory()
        return StageResult.completed({"done": True})


class _AlwaysLoopExecutor:
    """Always signals an evidence-gap loop back to retrieval."""

    def supports(self, stage_type: StageType) -> bool:
        return stage_type is StageType.VERIFY

    def execute(self, context: StageExecutionContext) -> StageResult:
        return StageResult.completed(
            {"loop": True}, control={"loop": "retrieve", "reason": "evidence_gap"}
        )


def _engine(
    tmp_path: Path,
    *,
    executors: dict[StageType, object] | None = None,
    guardrails: WorkflowGuardrails | None = None,
) -> tuple[WorkflowEngine, OrchestrationStore]:
    store = OrchestrationStore(tmp_path / "orch.db")
    store.initialize()
    from qwen_research.orchestration.stages import executor_registry

    merged: dict[StageType, object] = dict(executor_registry())
    merged[StageType.CUSTOM] = _NoopExecutor()
    if executors:
        merged.update(executors)
    engine = WorkflowEngine(store, guardrails=guardrails, executors=merged)  # type: ignore[arg-type]
    return engine, store


def test_run_completes_linear_plan(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    plan = _plan(store, task, _linear(("a", "b", "c")))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.COMPLETED
    assert all(s.status is StageStatus.COMPLETED for s in run.stages)


def test_pause_resume_cancel(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    plan = _plan(store, task, _linear(("a", "b", "c")))
    run = engine.create_run(task, plan)
    run = engine.start(run.run_id)
    assert run.status is RunStatus.RUNNING
    run = engine.pause(run.run_id)
    assert run.status is RunStatus.PAUSED
    run = engine.resume(run.run_id)
    assert run.status is RunStatus.RUNNING
    run = engine.cancel(run.run_id)
    assert run.status is RunStatus.CANCELLED


def test_step_executes_one_stage(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    plan = _plan(store, task, _linear(("a", "b")))
    run = engine.create_run(task, plan)
    run = engine.start(run.run_id)
    run, _ = engine.step(run.run_id)
    done = [s.stage_id for s in run.stages if s.status is StageStatus.COMPLETED]
    assert done == ["a"]


def test_dependencies_respected(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    stages = (
        ResearchStage(stage_id="a", type=StageType.CUSTOM, name="a", dependencies=()),
        ResearchStage(stage_id="b", type=StageType.CUSTOM, name="b", dependencies=("a",)),
        ResearchStage(stage_id="c", type=StageType.CUSTOM, name="c", dependencies=("a", "b")),
    )
    plan = _plan(store, task, stages)
    run = engine.create_run(task, plan)
    run, _ = engine.step(run.run_id)
    run, _ = engine.step(run.run_id)
    done = [s.stage_id for s in run.stages if s.status is StageStatus.COMPLETED]
    assert done == ["a", "b"]


def test_retry_on_transient_failure(tmp_path: Path) -> None:
    executor = _FailOnceExecutor(
        StageType.CUSTOM, lambda: RetrievalBackendUnavailable("backend down")
    )
    engine, store = _engine(tmp_path, executors={StageType.CUSTOM: executor})
    task = _task(store)
    stage = ResearchStage(
        stage_id="s",
        type=StageType.CUSTOM,
        name="s",
        retry_policy=RetryPolicy(max_attempts=3, retryable_errors=("RetrievalBackendUnavailable",)),
    )
    plan = _plan(store, task, (stage,))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.COMPLETED
    assert executor.calls == 2
    assert run.stages[0].attempts == 1


def test_non_retryable_failure_fails_run(tmp_path: Path) -> None:
    executor = _FailOnceExecutor(StageType.CUSTOM, lambda: ValueError("boom"))
    engine, store = _engine(tmp_path, executors={StageType.CUSTOM: executor})
    task = _task(store)
    stage = ResearchStage(
        stage_id="s",
        type=StageType.CUSTOM,
        name="s",
        retry_policy=RetryPolicy(max_attempts=3, retryable_errors=("RetrievalBackendUnavailable",)),
    )
    plan = _plan(store, task, (stage,))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.FAILED


def test_unsupported_capability_blocks(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    stages = (
        ResearchStage(
            stage_id="retrieve", type=StageType.RETRIEVE, name="retrieve", dependencies=()
        ),
    )
    plan = _plan(store, task, stages, criteria=CompletionCriteria(min_evidence_count=1))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.BLOCKED


def test_completion_criteria_partial(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    plan = _plan(
        store, task, _linear(("a", "b")), criteria=CompletionCriteria(min_evidence_count=5)
    )
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.PARTIAL


def test_loop_max_enforced(tmp_path: Path) -> None:
    loop_executor = _AlwaysLoopExecutor()
    guardrails = WorkflowGuardrails(max_retrieval_rounds=2)
    engine, store = _engine(
        tmp_path,
        executors={StageType.CUSTOM: _NoopExecutor(), StageType.VERIFY: loop_executor},
        guardrails=guardrails,
    )
    task = _task(store)
    stages = (
        ResearchStage(stage_id="retrieve", type=StageType.CUSTOM, name="retrieve", dependencies=()),
        ResearchStage(
            stage_id="verify", type=StageType.VERIFY, name="verify", dependencies=("retrieve",)
        ),
    )
    plan = _plan(store, task, stages)
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert run.status is RunStatus.BLOCKED
    assert run.counters["evidence_rounds"] == 2


def test_events_recorded(tmp_path: Path) -> None:
    engine, store = _engine(tmp_path)
    task = _task(store)
    plan = _plan(store, task, _linear(("a", "b")))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    events = engine.get_events(run.run_id)
    types = {e.event_type for e in events}
    assert EventType.CREATED in types
    assert EventType.COMPLETED in types


def test_no_duplicate_execution_on_rerun(tmp_path: Path) -> None:
    executor = _FailOnceExecutor(
        StageType.CUSTOM, lambda: RetrievalBackendUnavailable("backend down")
    )
    engine, store = _engine(tmp_path, executors={StageType.CUSTOM: executor})
    task = _task(store)
    stage = ResearchStage(
        stage_id="s",
        type=StageType.CUSTOM,
        name="s",
        retry_policy=RetryPolicy(max_attempts=3, retryable_errors=("RetrievalBackendUnavailable",)),
    )
    plan = _plan(store, task, (stage,))
    run = engine.create_run(task, plan)
    run = engine.execute_until_blocked(run.run_id)
    assert executor.calls == 2
    run2 = engine.execute_until_blocked(run.run_id)
    assert executor.calls == 2
    assert run2.status is RunStatus.COMPLETED
