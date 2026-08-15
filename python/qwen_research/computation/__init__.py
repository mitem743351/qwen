"""Deterministic computation layer.

Bounded, provenance-bearing analysis: DuckDB analytics, controlled Python
execution in a subprocess, seeded simulation, and structured results. The model
proposes and interprets; the runtime computes.
"""

from qwen_research.computation.analytics import DuckDBBackend, TableResult
from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.computation.datasets import DatasetResolver, ResolvedDataset
from qwen_research.computation.engine import ComputationEngine
from qwen_research.computation.models import (
    ColumnProfile,
    ComputationOperation,
    ComputationRequest,
    ComputationResult,
    ComputationStatus,
    ComputationSummary,
    DatasetProfile,
    DatasetReference,
    ExecutionProfile,
    ExecutionProfileSpec,
    ResultType,
    profile_spec,
)
from qwen_research.computation.registry import ComputationRegistry
from qwen_research.computation.sandbox import PythonExecutor
from qwen_research.computation.service import ComputationService
from qwen_research.computation.store import ComputationStore

__all__ = [
    "ArtifactStore",
    "ColumnProfile",
    "ComputationEngine",
    "ComputationOperation",
    "ComputationRegistry",
    "ComputationRequest",
    "ComputationResult",
    "ComputationService",
    "ComputationStatus",
    "ComputationStore",
    "ComputationSummary",
    "DatasetProfile",
    "DatasetReference",
    "DatasetResolver",
    "DuckDBBackend",
    "ExecutionProfile",
    "ExecutionProfileSpec",
    "PythonExecutor",
    "ResolvedDataset",
    "ResultType",
    "TableResult",
    "profile_spec",
]
