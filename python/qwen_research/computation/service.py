"""Computation application service.

The provider-independent façade used by the Research Runtime and MCP. It owns
dataset description, query/analysis submission, result retrieval, and dataset
freshness checks. It never executes computations itself — that is the engine's
job.
"""

from __future__ import annotations

import json

from qwen_research.computation.analytics import DuckDBBackend
from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.computation.datasets import DatasetResolver, ResolvedDataset
from qwen_research.computation.engine import ComputationEngine
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationRequest,
    ComputationResult,
    ComputationSummary,
    DatasetProfile,
    DatasetReference,
    ExecutionProfile,
)
from qwen_research.computation.sandbox import PythonExecutor
from qwen_research.computation.store import ComputationStore
from qwen_research.domain.errors import ComputationNotFoundError


class ComputationService:
    """Application-level deterministic computation operations."""

    def __init__(
        self,
        store: ComputationStore,
        resolver: DatasetResolver,
        *,
        duckdb: DuckDBBackend | None = None,
        python: PythonExecutor | None = None,
        artifacts: ArtifactStore | None = None,
        enable_python_execution: bool = False,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._engine = ComputationEngine(
            store,
            resolver,
            duckdb=duckdb,
            python=python,
            artifacts=artifacts,
            enable_python_execution=enable_python_execution,
        )

    def initialize(self) -> None:
        self._store.initialize()

    # -- reads -------------------------------------------------------------

    def describe_dataset(self, reference: DatasetReference) -> DatasetProfile:
        """Profile a dataset (schema, statistics, preview) without persisting."""
        resolved = self._resolver.resolve(reference)
        return self._engine.describe_dataset(resolved)

    def get_computation_result(self, project_id: str, computation_id: str) -> ComputationResult:
        return self._engine.get_result(project_id, computation_id)

    def list_computations(self, project_id: str) -> list[ComputationResult]:
        return self._engine.list_results(project_id)

    def get_computation_summaries(self, project_id: str) -> list[ComputationSummary]:
        return [ComputationSummary.from_result(r) for r in self._engine.list_results(project_id)]

    def computation_is_stale(self, computation_id: str) -> bool:
        """Return True if any input dataset has changed since the computation."""
        request = self._engine.get_request(computation_id)
        if request is None:
            raise ComputationNotFoundError(f"computation {computation_id!r} not found")
        result = self._engine.get_result(request.project_id, computation_id)
        if result is None:
            return False
        recorded = _recorded_hashes(result)
        for ref in request.input_refs:
            resolved = self._resolver.resolve(ref)
            if recorded.get(resolved.dataset_id) != resolved.content_hash:
                return True
        return False

    # -- writes ------------------------------------------------------------

    def run_query(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        query: str,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
        seed: int | None = None,
    ) -> ComputationResult:
        request = ComputationRequest.create(
            project_id,
            ComputationOperation.CUSTOM_SQL,
            input_refs=dataset_refs,
            parameters={"query": query, "parameters": parameters or {}},
            execution_profile=profile,
            seed=seed,
        )
        self._engine.submit(request)
        return self._engine.execute(request.computation_id)

    def run_analysis(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        operation: ComputationOperation,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
        seed: int | None = None,
    ) -> ComputationResult:
        request = ComputationRequest.create(
            project_id,
            operation,
            input_refs=dataset_refs,
            parameters=parameters or {},
            execution_profile=profile,
            seed=seed,
        )
        self._engine.submit(request)
        return self._engine.execute(request.computation_id)

    def run_python(
        self,
        project_id: str,
        source: str,
        *,
        profile: ExecutionProfile = ExecutionProfile.NUMERICAL,
        seed: int | None = None,
    ) -> ComputationResult:
        request = ComputationRequest.create(
            project_id,
            ComputationOperation.CUSTOM_PYTHON,
            parameters={"source": source},
            execution_profile=profile,
            seed=seed,
        )
        self._engine.submit(request)
        return self._engine.execute(request.computation_id)

    def submit(self, request: ComputationRequest) -> ComputationRequest:
        return self._engine.submit(request)

    def execute(self, computation_id: str) -> ComputationResult:
        return self._engine.execute(computation_id)

    def cancel(self, computation_id: str) -> ComputationResult:
        return self._engine.cancel(computation_id)

    def computation_ids_by_project(self) -> dict[str, frozenset[str]]:
        return self._store.computation_ids_by_project()


def _recorded_hashes(result: ComputationResult) -> dict[str, str]:
    raw = result.provenance.get("input_datasets", "[]")
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return {str(e["dataset_id"]): str(e["content_hash"]) for e in entries if isinstance(e, dict)}


__all__ = ["ComputationService", "ResolvedDataset"]
