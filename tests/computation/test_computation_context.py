"""ResearchContext computation-summary integration tests."""

from __future__ import annotations

from pathlib import Path

from computation_helpers import build_service, ref
from qwen_research.computation.models import ComputationOperation
from qwen_research.memory.context import ContextBudget
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_build_context_includes_computation_summaries(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.STATISTICS, {"column": "value"}
    )
    runtime = InMemoryResearchRuntime(computation=service)
    context = runtime.build_research_context("numbers", project_id="p")

    assert len(context.computations) == 1
    summary = context.computations[0]
    assert summary.computation_id == result.computation_id
    assert summary.operation == "statistics"
    assert summary.status == "completed"


def test_computation_summaries_are_bounded(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    runtime = InMemoryResearchRuntime(computation=service)
    budget = ContextBudget().max_computation_summaries
    for _ in range(budget + 3):
        service.run_analysis("p", (), ComputationOperation.CALCULATE, {"expression": "1 + 1"})

    context = runtime.build_research_context("anything", project_id="p")
    assert len(context.computations) == budget


def test_no_computation_service_yields_no_summaries(tmp_path: Path) -> None:
    runtime = InMemoryResearchRuntime()
    context = runtime.build_research_context("anything", project_id="p")
    assert context.computations == ()
