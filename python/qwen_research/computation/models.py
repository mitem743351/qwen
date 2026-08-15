"""Deterministic-computation domain model.

Provider-independent, transport-neutral value objects for the computation
layer. A computation is a *request* plus a *result*: the model proposes and
interprets, the runtime computes. Computation results are never claims and
never verified truth — a deterministic calculation can still be based on
incorrect inputs.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ComputationId, SessionId, TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class ComputationStatus(StrEnum):
    """Explicit lifecycle. A failure is never an empty result."""

    CREATED = "created"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RESOURCE_LIMIT = "resource_limit"
    CANCELLED = "cancelled"


class ComputationOperation(StrEnum):
    """The constrained operation vocabulary (never arbitrary shell)."""

    CALCULATE = "calculate"
    AGGREGATE = "aggregate"
    FILTER = "filter"
    JOIN = "join"
    DESCRIBE = "describe"
    SUMMARIZE = "summarize"
    GROUP = "group"
    COUNT = "count"
    STATISTICS = "statistics"
    CORRELATION = "correlation"
    REGRESSION = "regression"
    TRANSFORM = "transform"
    SIMULATE = "simulate"
    CUSTOM_PYTHON = "custom_python"
    CUSTOM_SQL = "custom_sql"


class ResultType(StrEnum):
    """Structured result categories — results are never flattened to a string."""

    SCALAR = "scalar"
    TABLE = "table"
    SERIES = "series"
    DISTRIBUTION = "distribution"
    STATISTICS = "statistics"
    PLOT = "plot"
    ARTIFACT = "artifact"
    TEXT_SUMMARY = "text_summary"
    ERROR = "error"


class ExecutionProfile(StrEnum):
    """Computation execution profiles with escalating capabilities."""

    SAFE = "safe"
    ANALYTICAL = "analytical"
    NUMERICAL = "numerical"
    SIMULATION = "simulation"


@serializable
@dataclasses.dataclass(frozen=True)
class ExecutionProfileSpec:
    """Resource limits and capability grants for an execution profile."""

    name: ExecutionProfile
    time_limit_seconds: float
    max_output_bytes: int
    max_input_bytes: int
    max_rows: int
    max_memory_bytes: int
    allowed_modules: tuple[str, ...]
    allowed_operations: tuple[ComputationOperation, ...]


#: Default profile specifications (bounded; never raw executor config via MCP).
def _profiles() -> dict[ExecutionProfile, ExecutionProfileSpec]:
    return {
        ExecutionProfile.SAFE: ExecutionProfileSpec(
            name=ExecutionProfile.SAFE,
            time_limit_seconds=5.0,
            max_output_bytes=64 * 1024,
            max_input_bytes=1 * 1024 * 1024,
            max_rows=10_000,
            max_memory_bytes=64 * 1024 * 1024,
            allowed_modules=("math", "statistics", "random", "json"),
            allowed_operations=(
                ComputationOperation.CALCULATE,
                ComputationOperation.DESCRIBE,
                ComputationOperation.SUMMARIZE,
                ComputationOperation.COUNT,
                ComputationOperation.STATISTICS,
                ComputationOperation.AGGREGATE,
                ComputationOperation.FILTER,
                ComputationOperation.GROUP,
                ComputationOperation.JOIN,
            ),
        ),
        ExecutionProfile.ANALYTICAL: ExecutionProfileSpec(
            name=ExecutionProfile.ANALYTICAL,
            time_limit_seconds=15.0,
            max_output_bytes=256 * 1024,
            max_input_bytes=16 * 1024 * 1024,
            max_rows=200_000,
            max_memory_bytes=256 * 1024 * 1024,
            allowed_modules=("math", "statistics", "random", "json"),
            allowed_operations=(
                ComputationOperation.CALCULATE,
                ComputationOperation.DESCRIBE,
                ComputationOperation.SUMMARIZE,
                ComputationOperation.COUNT,
                ComputationOperation.STATISTICS,
                ComputationOperation.CORRELATION,
                ComputationOperation.REGRESSION,
                ComputationOperation.AGGREGATE,
                ComputationOperation.FILTER,
                ComputationOperation.GROUP,
                ComputationOperation.JOIN,
                ComputationOperation.TRANSFORM,
                ComputationOperation.CUSTOM_SQL,
            ),
        ),
        ExecutionProfile.NUMERICAL: ExecutionProfileSpec(
            name=ExecutionProfile.NUMERICAL,
            time_limit_seconds=30.0,
            max_output_bytes=512 * 1024,
            max_input_bytes=64 * 1024 * 1024,
            max_rows=1_000_000,
            max_memory_bytes=512 * 1024 * 1024,
            allowed_modules=("math", "statistics", "random", "json"),
            allowed_operations=(
                ComputationOperation.CALCULATE,
                ComputationOperation.STATISTICS,
                ComputationOperation.CORRELATION,
                ComputationOperation.REGRESSION,
                ComputationOperation.TRANSFORM,
                ComputationOperation.SIMULATE,
                ComputationOperation.CUSTOM_SQL,
                ComputationOperation.CUSTOM_PYTHON,
            ),
        ),
        ExecutionProfile.SIMULATION: ExecutionProfileSpec(
            name=ExecutionProfile.SIMULATION,
            time_limit_seconds=60.0,
            max_output_bytes=1024 * 1024,
            max_input_bytes=128 * 1024 * 1024,
            max_rows=2_000_000,
            max_memory_bytes=1024 * 1024 * 1024,
            allowed_modules=("math", "statistics", "random", "json"),
            allowed_operations=(
                ComputationOperation.SIMULATE,
                ComputationOperation.STATISTICS,
                ComputationOperation.CUSTOM_PYTHON,
            ),
        ),
    }


PROFILE_SPECS: dict[ExecutionProfile, ExecutionProfileSpec] = _profiles()


def profile_spec(profile: ExecutionProfile) -> ExecutionProfileSpec:
    """Return the specification for *profile*."""
    return PROFILE_SPECS[profile]


@serializable
@dataclasses.dataclass(frozen=True)
class DatasetReference:
    """A controlled reference to a dataset.

    Inputs come only from controlled sources (corpus files, datasets, explicit
    parameters, prior artifacts) — never arbitrary OS paths. Resolution goes
    through the corpus security layer.
    """

    root_id: str | None = None
    relative_path: str | None = None
    document_id: str | None = None
    dataset_id: str | None = None
    artifact_id: str | None = None
    format: str | None = None  # "csv" | "json" | "parquet" | "sqlite"


@serializable
@dataclasses.dataclass(frozen=True)
class ColumnProfile:
    """One column's profile for a dataset."""

    name: str
    data_type: str
    null_count: int = 0
    distinct_count: int = 0
    min_value: str | None = None
    max_value: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class DatasetProfile:
    """A lightweight data-quality + schema profile for a dataset."""

    dataset_id: str
    row_count: int
    column_count: int
    columns: tuple[ColumnProfile, ...]
    size_bytes: int
    content_hash: str
    missing_value_count: int = 0
    duplicate_row_count: int = 0


@serializable
@dataclasses.dataclass(frozen=True)
class ComputationRequest:
    """A submitted, bounded computation."""

    computation_id: ComputationId
    project_id: str
    task_id: TaskId | None
    session_id: SessionId | None
    operation: ComputationOperation
    input_refs: tuple[DatasetReference, ...]
    parameters: dict[str, object]
    execution_profile: ExecutionProfile
    requested_output: ResultType | None
    deterministic: bool
    seed: int | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        project_id: str,
        operation: ComputationOperation,
        *,
        input_refs: tuple[DatasetReference, ...] = (),
        parameters: dict[str, object] | None = None,
        execution_profile: ExecutionProfile = ExecutionProfile.SAFE,
        requested_output: ResultType | None = None,
        deterministic: bool = True,
        seed: int | None = None,
        task_id: TaskId | None = None,
        session_id: SessionId | None = None,
    ) -> ComputationRequest:
        return cls(
            computation_id=ComputationId(new_id("computation")),
            project_id=project_id,
            task_id=task_id,
            session_id=session_id,
            operation=operation,
            input_refs=tuple(input_refs),
            parameters=dict(parameters or {}),
            execution_profile=execution_profile,
            requested_output=requested_output,
            deterministic=deterministic,
            seed=seed,
            created_at=utc_now(),
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ComputationResult:
    """The structured outcome of a computation, with full provenance."""

    computation_id: ComputationId
    project_id: str
    status: ComputationStatus
    operation: ComputationOperation
    result_type: ResultType
    value: object | None
    rows: int
    metrics: dict[str, object]
    artifact_refs: tuple[str, ...]
    provenance: dict[str, str]
    runtime_metadata: dict[str, str]
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

    @classmethod
    def create(
        cls,
        request: ComputationRequest,
        *,
        status: ComputationStatus,
        result_type: ResultType = ResultType.ERROR,
        value: object | None = None,
        rows: int = 0,
        metrics: dict[str, object] | None = None,
        artifact_refs: tuple[str, ...] = (),
        provenance: dict[str, str] | None = None,
        runtime_metadata: dict[str, str] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
    ) -> ComputationResult:
        return cls(
            computation_id=request.computation_id,
            project_id=request.project_id,
            status=status,
            operation=request.operation,
            result_type=result_type,
            value=value,
            rows=rows,
            metrics=dict(metrics or {}),
            artifact_refs=tuple(artifact_refs),
            provenance=dict(provenance or {}),
            runtime_metadata=dict(runtime_metadata or {}),
            started_at=started_at,
            completed_at=completed_at,
            error=error,
        )


@serializable
@dataclasses.dataclass(frozen=True)
class ComputationSummary:
    """A bounded, context-safe summary of a computation result."""

    computation_id: str
    project_id: str
    operation: str
    status: str
    result_type: str
    key_results: dict[str, object]
    artifact_refs: tuple[str, ...]
    provenance: dict[str, str]

    @classmethod
    def from_result(cls, result: ComputationResult) -> ComputationSummary:
        return cls(
            computation_id=result.computation_id,
            project_id=result.project_id,
            operation=result.operation.value,
            status=result.status.value,
            result_type=result.result_type.value,
            key_results=dict(result.metrics),
            artifact_refs=tuple(result.artifact_refs),
            provenance=dict(result.provenance),
        )
