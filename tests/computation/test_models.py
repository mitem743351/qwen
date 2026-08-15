"""Computation domain model tests."""

from __future__ import annotations

from qwen_research.computation.models import (
    ComputationOperation,
    ComputationRequest,
    ComputationResult,
    ComputationStatus,
    ExecutionProfile,
    ResultType,
    profile_spec,
)


def test_request_creation_defaults() -> None:
    request = ComputationRequest.create("p", ComputationOperation.STATISTICS)
    assert request.project_id == "p"
    assert request.operation is ComputationOperation.STATISTICS
    assert request.execution_profile is ExecutionProfile.SAFE
    assert request.deterministic is True
    assert request.seed is None
    assert request.input_refs == ()
    assert request.computation_id.startswith("computation_")


def test_result_creation_records_status() -> None:
    request = ComputationRequest.create("p", ComputationOperation.COUNT)
    result = ComputationResult.create(request, status=ComputationStatus.COMPLETED)
    assert result.status is ComputationStatus.COMPLETED
    assert result.computation_id == request.computation_id
    assert result.project_id == "p"


def test_failure_is_not_empty() -> None:
    request = ComputationRequest.create("p", ComputationOperation.COUNT)
    result = ComputationResult.create(
        request, status=ComputationStatus.FAILED, error="boom"
    )
    assert result.status is ComputationStatus.FAILED
    assert result.result_type is ResultType.ERROR
    assert result.error == "boom"


def test_profiles_are_bounded() -> None:
    safe = profile_spec(ExecutionProfile.SAFE)
    simulation = profile_spec(ExecutionProfile.SIMULATION)
    assert safe.time_limit_seconds <= simulation.time_limit_seconds
    assert safe.max_rows < simulation.max_rows
    # SIMULATE is not allowed in the SAFE profile.
    assert ComputationOperation.SIMULATE not in safe.allowed_operations
    assert ComputationOperation.SIMULATE in simulation.allowed_operations
    # CUSTOM_PYTHON is gated to NUMERICAL/SIMULATION.
    assert ComputationOperation.CUSTOM_PYTHON not in safe.allowed_operations
    assert ComputationOperation.CUSTOM_PYTHON in profile_spec(
        ExecutionProfile.NUMERICAL
    ).allowed_operations


def test_statuses_are_distinct() -> None:
    statuses = {s.value for s in ComputationStatus}
    assert statuses == {
        "created",
        "validating",
        "running",
        "completed",
        "failed",
        "timed_out",
        "resource_limit",
        "cancelled",
    }
