"""Restart/resume tests: persistence across process restart, idempotency."""

from __future__ import annotations

from pathlib import Path

from orchestration_helpers import build_stack
from qwen_research.orchestration.capabilities import capability_registry_from_runtime
from qwen_research.orchestration.service import OrchestrationService
from qwen_research.orchestration.store import OrchestrationStore


def _count_memory(memory_store: object) -> int:
    return len(memory_store.get_research_memory("p"))  # type: ignore[attr-defined]


def _count_claims(vstore: object) -> int:
    return len(vstore.get_claims("p"))  # type: ignore[attr-defined]


def test_restart_and_resume_idempotent(tmp_path: Path) -> None:
    s = build_stack(tmp_path)
    runtime = s["runtime"]

    # --- first process: plan + run to completion ---
    task, plan = runtime.plan_research("what is the surface code threshold", project_id="p")
    run = runtime.start_research(plan.plan_id)
    assert run.status.value == "completed"
    memory_before = _count_memory(s["memory_store"])
    claims_before = _count_claims(s["verification_store"])
    assert memory_before >= 1

    # --- second process: reopen the same orchestration DB and load state ---
    ostore2 = OrchestrationStore(tmp_path / "orchestration.db")
    ostore2.initialize()
    service2 = OrchestrationService(
        ostore2,
        runtime=runtime,
        capabilities=capability_registry_from_runtime(
            retriever=True, memory=True, verification=True, computation=True
        ),
    )

    loaded = service2.get_run(run.run_id)
    assert loaded.status.value == "completed"
    assert service2.get_plan(plan.plan_id).plan_id == plan.plan_id
    assert service2.get_events(run.run_id)

    # Resuming a completed run must be a no-op: no duplicate memory or claims.
    service2.resume_research(run.run_id)
    assert _count_memory(s["memory_store"]) == memory_before
    assert _count_claims(s["verification_store"]) == claims_before


def test_pause_then_resume_completes(tmp_path: Path) -> None:
    s = build_stack(tmp_path)
    runtime = s["runtime"]
    task, plan = runtime.plan_research("what is the surface code threshold", project_id="p")

    # Create a run but do not auto-execute it: step through the engine manually.
    service = runtime._orchestration  # noqa: SLF001
    run = service._engine.create_run(  # noqa: SLF001
        service._store.get_task(task.task_id),  # noqa: SLF001
        plan,
    )
    run = service._engine.start(run.run_id)  # noqa: SLF001
    run, _ = service._engine.step(run.run_id)  # noqa: SLF001
    # Pause mid-run, then resume and execute to completion.
    run = service._engine.pause(run.run_id)  # noqa: SLF001
    assert run.status.value == "paused"
    run = service._engine.resume(run.run_id)  # noqa: SLF001
    assert run.status.value == "running"
    run = service._engine.execute_until_blocked(run.run_id)  # noqa: SLF001
    assert run.status.value == "completed"
