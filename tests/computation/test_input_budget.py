"""max_input_bytes enforcement and dataset-load deadline tests.

Verifies that (a) ``max_input_bytes`` is enforced as an **aggregate**
per-computation budget (the sum of all input dataset sizes), and (b) dataset
loading runs inside the same execution deadline as the query.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from computation_helpers import build_data_dir, build_service, ref
from qwen_research.computation.analytics import DuckDBBackend
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationStatus,
    ExecutionProfile,
)
from qwen_research.domain.errors import ExecutionTimeoutError


def _write_bytes(data: Path, name: str, approx_bytes: int) -> Path:
    """Write a CSV file of roughly *approx_bytes* bytes (a little under)."""
    path = data / name
    # Each line is ~600 bytes; pick a line count that stays just under the target.
    line = "x" * 600 + "\n"  # 601 bytes/line
    n = approx_bytes // 601
    path.write_text("v\n" + line * n)
    return path


def test_max_input_bytes_enforced_aggregate(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    # SAFE profile's max_input_bytes is 1 MiB. Two files, each ~600 KiB (under
    # the budget individually), sum to ~1.2 MiB (over) → must be rejected.
    _write_bytes(data, "a.csv", 600 * 1024)
    _write_bytes(data, "b.csv", 600 * 1024)

    result = service.run_analysis(
        "p",
        (ref(data, "a.csv"), ref(data, "b.csv")),
        ComputationOperation.COUNT,
        profile=ExecutionProfile.SAFE,
    )
    assert result.status is ComputationStatus.RESOURCE_LIMIT
    assert "max_input_bytes" in (result.error or "")


def test_max_input_bytes_single_over_budget(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    _write_bytes(data, "big.csv", 2 * 1024 * 1024)  # 2 MiB > 1 MiB budget

    result = service.run_analysis(
        "p",
        (ref(data, "big.csv"),),
        ComputationOperation.COUNT,
        profile=ExecutionProfile.SAFE,
    )
    assert result.status is ComputationStatus.RESOURCE_LIMIT


def test_max_input_bytes_under_budget_allowed(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    # A small dataset stays well under budget and must succeed.
    result = service.run_analysis(
        "p",
        (ref(data, "numbers.csv"),),
        ComputationOperation.COUNT,
        profile=ExecutionProfile.SAFE,
    )
    assert result.status is ComputationStatus.COMPLETED


def test_input_budget_checked_before_execution(tmp_path: Path) -> None:
    service, store, _, _, data = build_service(tmp_path)
    _write_bytes(data, "big.csv", 2 * 1024 * 1024)
    # The budget violation is raised during _run (not submit); the request is
    # persisted but its result is a RESOURCE_LIMIT, not a raw exception.
    result = service.run_analysis(
        "p",
        (ref(data, "big.csv"),),
        ComputationOperation.COUNT,
        profile=ExecutionProfile.SAFE,
    )
    assert result.status is ComputationStatus.RESOURCE_LIMIT
    assert store.get_result("p", result.computation_id) is not None


def test_dataset_loading_covered_by_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dataset loading runs inside the same deadline as the query.

    A slow load must be interrupted and raise ``ExecutionTimeoutError`` — under
    the previous implementation loading ran synchronously outside the timed
    region, so this would have completed (and then failed on a missing table)
    rather than timing out.
    """
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    from qwen_research.computation.datasets import DatasetResolver
    from qwen_research.computation.models import DatasetReference
    from qwen_research.corpus.config import CorpusConfig, CorpusRoot

    config = CorpusConfig(
        roots=(CorpusRoot(root_id="data", path=str(data), read_only=True, recursive=True),)
    )
    resolved = DatasetResolver(config).resolve(
        DatasetReference(root_id="data", relative_path="numbers.csv")
    )

    def slow_load(self: DuckDBBackend, con: object, datasets: list) -> dict[str, str]:
        time.sleep(2.0)
        return {"t0": "t0"}

    monkeypatch.setattr(DuckDBBackend, "_load", slow_load)

    with pytest.raises(ExecutionTimeoutError):
        backend.count([resolved], max_rows=10, time_limit_seconds=0.1)
