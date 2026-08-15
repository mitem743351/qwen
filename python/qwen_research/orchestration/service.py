"""Research orchestration application service.

The provider-independent façade used by the Research Runtime and MCP. It owns
deterministic planning, workflow-run creation/execution/control, status and
summary assembly. It never invokes a model and never performs subsystem work
itself — it orchestrates the runtime's capabilities.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import TYPE_CHECKING

from qwen_research.domain.errors import (
    PlanNotFoundError,
    ResearchTaskNotFoundError,
    RunNotFoundError,
)
from qwen_research.domain.reasoning import get_profile
from qwen_research.orchestration.capabilities import CapabilityRegistry
from qwen_research.orchestration.engine import WorkflowEngine
from qwen_research.orchestration.models import (
    ComputationSpec,
    ResearchPlan,
    ResearchStatus,
    ResearchTask,
    RunStatus,
    TaskType,
    WorkflowEvent,
    WorkflowGuardrails,
    WorkflowRun,
    as_str_tuple,
    is_terminal_run_status,
)
from qwen_research.orchestration.planning import ResearchPlanner
from qwen_research.orchestration.store import OrchestrationStore

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.orchestration.stages import StageRuntime


class OrchestrationService:
    """Deterministic research orchestration (planner + workflow engine)."""

    def __init__(
        self,
        store: OrchestrationStore,
        *,
        runtime: StageRuntime | None = None,
        capabilities: CapabilityRegistry | None = None,
        guardrails: WorkflowGuardrails | None = None,
        planner: ResearchPlanner | None = None,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._capabilities = capabilities
        self._planner = planner or ResearchPlanner(capabilities=capabilities)
        self._engine = WorkflowEngine(
            store, runtime=runtime, guardrails=guardrails or WorkflowGuardrails()
        )

    def initialize(self) -> None:
        self._store.initialize()

    # -- planning ----------------------------------------------------------

    def plan_research(
        self,
        description: str,
        *,
        project_id: str = "default",
        session_id: str = "default",
        task_type: TaskType | None = None,
        profile: str = "DEEP",
        subquestions: tuple[str, ...] = (),
        computation: ComputationSpec | None = None,
    ) -> tuple[ResearchTask, ResearchPlan]:
        """Classify and plan a research task deterministically (no model call)."""
        resolved_type = self._planner.classify_task_type(description, task_type)
        complexity = self._planner.classify_complexity(
            description, task_type=resolved_type, profile_name=profile
        )
        task = ResearchTask.create(
            project_id,
            description,
            resolved_type,
            complexity,
            profile,
            session_id=session_id,
        )
        plan = self._planner.create_plan(
            task,
            profile=get_profile(profile),
            subquestions=subquestions,
            computation=computation,
        )
        task = dataclasses.replace(
            task, plan_id=plan.plan_id, status="planned", updated_at=_now()
        )
        self._store.save_task(task)
        self._store.save_plan(plan, project_id=project_id)
        return task, plan

    # -- execution ---------------------------------------------------------

    def start_research(self, plan_id: str) -> WorkflowRun:
        """Create a run and execute it to completion/block (synchronous)."""
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(f"plan {plan_id!r} not found")
        task = self._store.get_task(plan.task_id)
        if task is None:
            raise ResearchTaskNotFoundError(f"research task {plan.task_id!r} not found")
        run = self._engine.create_run(task, plan)
        run = self._engine.execute_until_blocked(run.run_id)
        task = dataclasses.replace(
            task, workflow_id=run.run_id, status=run.status.value, updated_at=_now()
        )
        self._store.save_task(task)
        return run

    def resume_research(self, run_id: str) -> WorkflowRun:
        run = self._engine.resume(run_id)
        if run.status is RunStatus.RUNNING:
            run = self._engine.execute_until_blocked(run_id)
        self._sync_task(run)
        return run

    def pause_research(self, run_id: str) -> WorkflowRun:
        run = self._engine.pause(run_id)
        self._sync_task(run)
        return run

    def cancel_research(self, run_id: str) -> WorkflowRun:
        run = self._engine.cancel(run_id)
        self._sync_task(run)
        return run

    def get_run(self, run_id: str) -> WorkflowRun:
        run = self._store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"run {run_id!r} not found")
        return run

    def get_plan(self, plan_id: str) -> ResearchPlan:
        plan = self._store.get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(f"plan {plan_id!r} not found")
        return plan

    def get_events(self, run_id: str) -> list[WorkflowEvent]:
        return self._store.get_events(run_id)

    # -- status / summary --------------------------------------------------

    def get_research_status(self, run_id: str) -> ResearchStatus:
        run = self.get_run(run_id)
        total = len(run.stages)
        done = sum(1 for s in run.stages if s.status.value in ("completed", "skipped"))
        progress = (done / total) if total else 0.0
        if is_terminal_run_status(run.status) and run.status is RunStatus.COMPLETED:
            progress = 1.0
        return ResearchStatus(
            task_id=run.task_id,
            run_id=run.run_id,
            status=run.status.value,
            current_stage=run.current_stage,
            progress=round(progress, 4),
            degradation=run.degradation,
            unresolved_questions=(),
            blocking_issues=run.errors,
            started_at=run.started_at,
            updated_at=run.updated_at,
        )

    def get_research_summary(self, run_id: str) -> dict[str, object]:
        run = self.get_run(run_id)
        task = self._store.get_task(run.task_id)
        outputs = run.outputs
        return {
            "task_id": run.task_id,
            "run_id": run.run_id,
            "status": run.status.value,
            "title": task.title if task else "",
            "key_claims": len(as_str_tuple(outputs.get("claims"))),
            "supporting_evidence": len(as_str_tuple(outputs.get("evidence"))),
            "contradictions": len(as_str_tuple(outputs.get("contradictions"))),
            "verification_summary": list(as_str_tuple(outputs.get("verification_statuses"))),
            "computation_summary": list(as_str_tuple(outputs.get("computations"))),
            "open_questions": list(as_str_tuple(outputs.get("unresolved_questions"))),
            "artifact_refs": list(as_str_tuple(outputs.get("artifacts"))),
            "degradation": list(run.degradation),
            "accounting": dict(run.accounting),
        }

    def _sync_task(self, run: WorkflowRun) -> None:
        task = self._store.get_task(run.task_id)
        if task is not None:
            self._store.save_task(
                dataclasses.replace(task, status=run.status.value, updated_at=_now())
            )


def _now() -> datetime:
    from qwen_research.common.timestamps import utc_now

    return utc_now()
