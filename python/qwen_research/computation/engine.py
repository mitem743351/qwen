"""The deterministic ComputationEngine.

Validates, authorizes, resolves inputs, dispatches to execution backends
(DuckDB analytics and a controlled Python subprocess), records provenance
(code/query hashes, dataset freshness, software versions), registers
artifacts, and persists structured results. The engine never executes shell
or arbitrary host commands.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, cast

from qwen_research.common.timestamps import utc_now
from qwen_research.computation.analytics import DuckDBBackend, TableResult
from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.computation.calculator import calculate
from qwen_research.computation.datasets import DatasetResolver, ResolvedDataset
from qwen_research.computation.descriptive import (
    describe,
    linear_regression,
    pearson_correlation,
)
from qwen_research.computation.hashes import code_hash, query_hash
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationRequest,
    ComputationResult,
    ComputationStatus,
    DatasetProfile,
    DatasetReference,
    ResultType,
    profile_spec,
)
from qwen_research.computation.registry import ComputationRegistry
from qwen_research.computation.sandbox import PythonExecutor
from qwen_research.computation.simulation import simulate
from qwen_research.computation.store import ComputationStore
from qwen_research.domain.errors import (
    ComputationError,
    ComputationNotFoundError,
    ComputationValidationError,
    DatasetError,
    ExecutionTimeoutError,
    QueryValidationError,
    ResourceLimitError,
)

#: Rows returned inline; larger results become artifacts with a sample.
_MAX_INLINE_ROWS = 100


@dataclass(frozen=True)
class OperationOutcome:
    result_type: ResultType
    value: object | None
    rows: int
    metrics: dict[str, object]
    artifact_refs: tuple[str, ...]
    provenance: dict[str, str]


class ComputationEngine:
    """Provider-independent deterministic computation pipeline."""

    def __init__(
        self,
        store: ComputationStore,
        resolver: DatasetResolver,
        *,
        duckdb: DuckDBBackend | None = None,
        python: PythonExecutor | None = None,
        artifacts: ArtifactStore | None = None,
        registry: ComputationRegistry | None = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._duckdb = duckdb or DuckDBBackend()
        self._python = python or PythonExecutor()
        self._artifacts = artifacts or ArtifactStore("workspaces/computation")
        self._registry = registry or ComputationRegistry()

    def submit(self, request: ComputationRequest) -> ComputationRequest:
        """Validate and persist a request in the CREATED state."""
        self._validate(request)
        self._store.save_request(request)
        return request

    def execute(self, computation_id: str) -> ComputationResult:
        """Run a persisted request and store its result."""
        request = self._store.get_request(computation_id)
        if request is None:
            raise ComputationNotFoundError(f"computation {computation_id!r} not found")
        started = utc_now()
        status = ComputationStatus.COMPLETED
        error: str | None = None
        try:
            outcome = self._run(request)
        except ExecutionTimeoutError as exc:
            status = ComputationStatus.TIMED_OUT
            error = str(exc)
        except ResourceLimitError as exc:
            status = ComputationStatus.RESOURCE_LIMIT
            error = str(exc)
        except ComputationError as exc:
            status = ComputationStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 — never leak internal failures
            status = ComputationStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"

        if status is ComputationStatus.COMPLETED:
            result = ComputationResult.create(
                request,
                status=ComputationStatus.COMPLETED,
                result_type=outcome.result_type,
                value=outcome.value,
                rows=outcome.rows,
                metrics=outcome.metrics,
                artifact_refs=outcome.artifact_refs,
                provenance=outcome.provenance,
                runtime_metadata=self._runtime_metadata(),
                started_at=started,
                completed_at=utc_now(),
            )
        else:
            result = ComputationResult.create(
                request,
                status=status,
                result_type=ResultType.ERROR,
                error=error,
                started_at=started,
                completed_at=utc_now(),
            )
        self._store.save_result(result)
        return result

    def get_result(self, project_id: str, computation_id: str) -> ComputationResult:
        result = self._store.get_result(project_id, computation_id)
        if result is None:
            raise ComputationNotFoundError(f"computation {computation_id!r} not found")
        return result

    def get_request(self, computation_id: str) -> ComputationRequest | None:
        return self._store.get_request(computation_id)

    def resolve(self, reference: DatasetReference) -> ResolvedDataset:
        return self._resolver.resolve(reference)

    def describe_dataset(
        self, resolved: ResolvedDataset, *, max_rows: int = 10_000
    ) -> DatasetProfile:
        return self._duckdb.describe_dataset(resolved, max_rows=max_rows)

    def list_results(self, project_id: str) -> list[ComputationResult]:
        return self._store.list_results(project_id)

    def cancel(self, computation_id: str) -> None:
        request = self._store.get_request(computation_id)
        if request is None:
            raise ComputationNotFoundError(f"computation {computation_id!r} not found")
        result = ComputationResult.create(
            request, status=ComputationStatus.CANCELLED, result_type=ResultType.ERROR
        )
        self._store.save_result(result)

    # -- validation --------------------------------------------------------

    def _validate(self, request: ComputationRequest) -> None:
        if not request.parameters and request.operation in (
            ComputationOperation.CUSTOM_SQL,
            ComputationOperation.CUSTOM_PYTHON,
            ComputationOperation.SIMULATE,
            ComputationOperation.CALCULATE,
        ):
            # These require parameters (query/source/expression/distribution).
            pass
        spec = profile_spec(request.execution_profile)
        if request.operation not in spec.allowed_operations:
            raise ComputationValidationError(
                f"operation {request.operation.value!r} not allowed in profile "
                f"{request.execution_profile.value!r}"
            )

    # -- dispatch ----------------------------------------------------------

    def _run(self, request: ComputationRequest) -> OperationOutcome:
        spec = profile_spec(request.execution_profile)
        resolved = [self._resolver.resolve(ref) for ref in request.input_refs]
        max_rows = spec.max_rows

        op = request.operation
        if op is ComputationOperation.DESCRIBE:
            outcome = self._describe(resolved, max_rows)
        elif op is ComputationOperation.SUMMARIZE:
            outcome = self._summarize(resolved, max_rows)
        elif op is ComputationOperation.COUNT:
            outcome = self._count(resolved, max_rows)
        elif op is ComputationOperation.AGGREGATE:
            outcome = self._aggregate(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.GROUP:
            outcome = self._group(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.FILTER:
            outcome = self._filter(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.JOIN:
            outcome = self._join(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.STATISTICS:
            outcome = self._statistics(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.CORRELATION:
            outcome = self._correlation(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.REGRESSION:
            outcome = self._regression(resolved, request.parameters, max_rows)
        elif op is ComputationOperation.CALCULATE:
            outcome = self._calculate(request.parameters)
        elif op is ComputationOperation.SIMULATE:
            outcome = self._simulate(request)
        elif op is ComputationOperation.CUSTOM_SQL:
            outcome = self._custom_sql(resolved, request, max_rows)
        elif op is ComputationOperation.CUSTOM_PYTHON:
            outcome = self._custom_python(request, max_rows)
        else:
            raise ComputationValidationError(f"unsupported operation {op.value!r}")
        return self._with_freshness(outcome, resolved)

    def _with_freshness(
        self, outcome: OperationOutcome, resolved: list[ResolvedDataset]
    ) -> OperationOutcome:
        """Attach input-dataset freshness (stable identity + content hash)."""
        provenance = dict(outcome.provenance)
        provenance["input_datasets"] = json.dumps(
            [
                {"dataset_id": r.dataset_id, "content_hash": r.content_hash, "path": r.path}
                for r in resolved
            ],
            sort_keys=True,
        )
        return OperationOutcome(
            outcome.result_type,
            outcome.value,
            outcome.rows,
            outcome.metrics,
            outcome.artifact_refs,
            provenance,
        )

    # -- handlers ----------------------------------------------------------

    def _describe(self, resolved: list[ResolvedDataset], max_rows: int) -> OperationOutcome:
        if len(resolved) != 1:
            raise DatasetError("describe requires exactly one dataset")
        profile = self._duckdb.describe_dataset(resolved[0], max_rows=max_rows)
        return OperationOutcome(
            ResultType.STATISTICS,
            _profile_to_dict(profile),
            0,
            {"row_count": profile.row_count, "column_count": profile.column_count},
            (),
            {"dataset_id": profile.dataset_id, "content_hash": profile.content_hash},
        )

    def _summarize(self, resolved: list[ResolvedDataset], max_rows: int) -> OperationOutcome:
        if len(resolved) != 1:
            raise DatasetError("summarize requires exactly one dataset")
        profile = self._duckdb.describe_dataset(resolved[0], max_rows=max_rows)
        return OperationOutcome(
            ResultType.STATISTICS,
            _profile_to_dict(profile),
            0,
            {
                "row_count": profile.row_count,
                "missing_value_count": profile.missing_value_count,
                "duplicate_row_count": profile.duplicate_row_count,
            },
            (),
            {"dataset_id": profile.dataset_id, "content_hash": profile.content_hash},
        )

    def _count(self, resolved: list[ResolvedDataset], max_rows: int) -> OperationOutcome:
        table = self._duckdb.count(resolved, max_rows=max_rows)
        return OperationOutcome(
            ResultType.SCALAR,
            table.rows[0][0] if table.rows else 0,
            0,
            {"count": table.rows[0][0] if table.rows else 0},
            (),
            {},
        )

    def _aggregate(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        column = _require_str(params, "column")
        function = _require_str(params, "function")
        table = self._duckdb.aggregate(resolved, column, function, max_rows=max_rows)
        value = table.rows[0][0] if table.rows else None
        return OperationOutcome(ResultType.SCALAR, value, 0, {}, (), {})

    def _group(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        group_by = _require_str(params, "group_by")
        column = _require_str(params, "column")
        function = _require_str(params, "function")
        table = self._duckdb.group(resolved, group_by, column, function, max_rows=max_rows)
        return self._table_outcome(table)

    def _filter(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        predicate = _require_str(params, "predicate")
        table = self._duckdb.filter(resolved, predicate, max_rows=max_rows)
        return self._table_outcome(table)

    def _join(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        left_key = _require_str(params, "left_key")
        right_key = _require_str(params, "right_key")
        table = self._duckdb.join(resolved, left_key, right_key, max_rows=max_rows)
        return self._table_outcome(table)

    def _statistics(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        column = _require_str(params, "column")
        values = self._duckdb.numeric_column(resolved, column, max_rows=max_rows)
        stats = describe(values)
        return OperationOutcome(ResultType.STATISTICS, stats, 0, {}, (), {"column": column})

    def _correlation(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        x = self._duckdb.numeric_column(resolved, _require_str(params, "x"), max_rows=max_rows)
        y = self._duckdb.numeric_column(resolved, _require_str(params, "y"), max_rows=max_rows)
        result = pearson_correlation(x, y)
        return OperationOutcome(ResultType.STATISTICS, result, 0, {}, (), {})

    def _regression(
        self, resolved: list[ResolvedDataset], params: dict[str, object], max_rows: int
    ) -> OperationOutcome:
        x = self._duckdb.numeric_column(resolved, _require_str(params, "x"), max_rows=max_rows)
        y = self._duckdb.numeric_column(resolved, _require_str(params, "y"), max_rows=max_rows)
        result = linear_regression(x, y)
        return OperationOutcome(ResultType.STATISTICS, result, 0, {}, (), {})

    def _calculate(self, params: dict[str, object]) -> OperationOutcome:
        expression = _require_str(params, "expression")
        raw_variables = params.get("variables", {})
        variables: dict[str, float] = {}
        if isinstance(raw_variables, dict):
            for key, value in raw_variables.items():
                if value is not None:
                    variables[str(key)] = float(cast(Any, value))
        value = calculate(expression, variables)
        return OperationOutcome(ResultType.SCALAR, value, 0, {}, (), {"expression": expression})

    def _simulate(self, request: ComputationRequest) -> OperationOutcome:
        params = request.parameters
        distribution = _require_str(params, "distribution")
        seed = request.seed
        if seed is None:
            raise ComputationValidationError("simulate requires a seed")
        iterations = int(cast(Any, params.get("iterations", 1000)))
        result = simulate(
            distribution=distribution,
            seed=seed,
            iterations=iterations,
            parameters={k: v for k, v in params.items() if k not in ("distribution", "iterations")},
        )
        sample = result.pop("sample", [])
        artifact_ref = self._artifacts.save_json({"sample": sample, "summary": result})
        return OperationOutcome(
            ResultType.DISTRIBUTION,
            result,
            iterations,
            {"iterations": iterations, "seed": seed},
            (artifact_ref,),
            {"seed": str(seed), "distribution": distribution},
        )

    def _custom_sql(
        self, resolved: list[ResolvedDataset], request: ComputationRequest, max_rows: int
    ) -> OperationOutcome:
        query = _require_str(request.parameters, "query")
        parameters = request.parameters.get("parameters", {})
        if not isinstance(parameters, dict):
            raise QueryValidationError("query parameters must be an object")
        table = self._duckdb.run_query(
            resolved,
            query,
            parameters,
            max_rows=max_rows,
            max_output_bytes=profile_spec(request.execution_profile).max_output_bytes,
        )
        return self._table_outcome(table, provenance={"query_hash": query_hash(query)})

    def _custom_python(self, request: ComputationRequest, max_rows: int) -> OperationOutcome:
        source = _require_str(request.parameters, "source")
        spec = profile_spec(request.execution_profile)
        value = self._python.execute(
            source,
            seed=request.seed,
            time_limit_seconds=spec.time_limit_seconds,
            max_output_bytes=spec.max_output_bytes,
            max_memory_bytes=spec.max_memory_bytes,
        )
        if isinstance(value, (dict, list, tuple, str, int, float, bool)) or value is None:
            rows = len(value) if isinstance(value, list) else 0
            return OperationOutcome(
                ResultType.SCALAR if not isinstance(value, list) else ResultType.SERIES,
                value,
                rows,
                {},
                (),
                {"code_hash": code_hash(source)},
            )
        return OperationOutcome(
            ResultType.SCALAR,
            repr(value),
            0,
            {},
            (),
            {"code_hash": code_hash(source)},
        )

    # -- helpers -----------------------------------------------------------

    def _table_outcome(
        self, table: TableResult, *, provenance: dict[str, str] | None = None
    ) -> OperationOutcome:
        if table.row_count <= _MAX_INLINE_ROWS and not table.truncated:
            value = {
                "columns": list(table.columns),
                "rows": [list(r) for r in table.rows],
                "row_count": table.row_count,
                "truncated": False,
            }
            return OperationOutcome(
                ResultType.TABLE, value, table.row_count, {}, (), provenance or {}
            )
        # Large result → artifact + bounded sample.
        artifact_ref = self._artifacts.save_csv(table.columns, table.rows)
        value = {
            "columns": list(table.columns),
            "rows": [list(r) for r in table.rows[:_MAX_INLINE_ROWS]],
            "row_count": table.row_count,
            "truncated": True,
            "artifact_ref": artifact_ref,
        }
        return OperationOutcome(
            ResultType.ARTIFACT,
            value,
            table.row_count,
            {"truncated": True, "sample_rows": min(len(table.rows), _MAX_INLINE_ROWS)},
            (artifact_ref,),
            provenance or {},
        )

    def _runtime_metadata(self) -> dict[str, str]:
        duckdb_version = ""
        try:
            import duckdb

            duckdb_version = duckdb.__version__
        except Exception:  # noqa: BLE001 — best-effort metadata
            pass
        return {
            "python_version": sys.version.split()[0],
            "duckdb_version": duckdb_version,
        }


def _require_str(params: dict[str, object], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ComputationValidationError(f"parameter {key!r} is required and must be a string")
    return value


def _profile_to_dict(profile: DatasetProfile) -> dict[str, object]:
    return {
        "dataset_id": profile.dataset_id,
        "row_count": profile.row_count,
        "column_count": profile.column_count,
        "columns": [
            {
                "name": c.name,
                "data_type": c.data_type,
                "null_count": c.null_count,
                "distinct_count": c.distinct_count,
                "min": c.min_value,
                "max": c.max_value,
            }
            for c in profile.columns
        ],
        "size_bytes": profile.size_bytes,
        "content_hash": profile.content_hash,
        "missing_value_count": profile.missing_value_count,
        "duplicate_row_count": profile.duplicate_row_count,
    }
