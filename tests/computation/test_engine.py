"""ComputationEngine + service end-to-end tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from computation_helpers import build_service, ref
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationStatus,
    ExecutionProfile,
)
from qwen_research.domain.errors import ComputationNotFoundError, ComputationValidationError


def _value(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], result.value)


def test_describe_dataset(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    profile = service.describe_dataset(ref(data, "numbers.csv"))
    assert profile.row_count == 5
    assert profile.column_count == 2


def test_run_analysis_statistics(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.STATISTICS, {"column": "value"}
    )
    assert result.status is ComputationStatus.COMPLETED
    assert _value(result)["count"] == 5
    assert _value(result)["mean"] == 3.6


def test_run_analysis_aggregate(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.AGGREGATE,
        {"column": "value", "function": "sum"},
    )
    assert result.status is ComputationStatus.COMPLETED
    assert result.value == 18.0


def test_run_analysis_group(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.GROUP,
        {"group_by": "group", "column": "value", "function": "mean"},
    )
    assert result.status is ComputationStatus.COMPLETED
    assert _value(result)["rows"] == [["A", 1.5], ["B", 5.0]]


def test_run_query_parameterized(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_query(
        "p", (ref(data, "numbers.csv"),), "SELECT * FROM t0 WHERE value >= :v", {"v": 3.0}
    )
    assert result.status is ComputationStatus.COMPLETED
    assert _value(result)["row_count"] == 3


def test_run_query_escape_rejected(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_query("p", (ref(data, "numbers.csv"),), "COPY t0 TO '/tmp/x.csv'")
    assert result.status is ComputationStatus.FAILED


def test_calculate(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    result = service.run_analysis(
        "p", (), ComputationOperation.CALCULATE, {"expression": "sqrt(16) + 2"}
    )
    assert result.status is ComputationStatus.COMPLETED
    assert result.value == 6.0


def test_simulate_persists_seed(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    result = service.run_analysis(
        "p", (), ComputationOperation.SIMULATE,
        {"distribution": "normal", "iterations": 100},
        seed=42, profile=ExecutionProfile.SIMULATION,
    )
    assert result.status is ComputationStatus.COMPLETED
    assert result.provenance["seed"] == "42"
    assert len(result.artifact_refs) == 1


def test_custom_python(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    result = service.run_python("p", "RESULT = [i * i for i in range(4)]")
    assert result.status is ComputationStatus.COMPLETED
    assert result.value == [0, 1, 4, 9]


def test_operation_profile_restriction(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    # SIMULATE is not allowed in the default ANALYTICAL profile → validation error.
    with pytest.raises(ComputationValidationError):
        service.run_analysis(
            "p", (), ComputationOperation.SIMULATE, {"distribution": "normal"}, seed=1
        )


def test_get_result_missing_raises(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    with pytest.raises(ComputationNotFoundError):
        service.get_computation_result("p", "computation_missing")


def test_code_hash_recorded(tmp_path: Path) -> None:
    service, _, _, _, _ = build_service(tmp_path)
    result = service.run_python("p", "RESULT = 1 + 1")
    assert "code_hash" in result.provenance


def test_dataset_freshness_detected(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.COUNT
    )
    computation_id = result.computation_id
    assert service.computation_is_stale(computation_id) is False
    # Mutate the dataset → the computation becomes stale.
    (data / "numbers.csv").write_text("group,value\nA,1.0\nA,2.0\n")
    assert service.computation_is_stale(computation_id) is True


def test_project_isolation(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    result = service.run_analysis(
        "projA", (ref(data, "numbers.csv"),), ComputationOperation.COUNT
    )
    assert service.get_computation_result("projA", result.computation_id) is not None
    with pytest.raises(ComputationNotFoundError):
        service.get_computation_result("projB", result.computation_id)
