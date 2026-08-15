"""Adversarial DuckDB workload tests: timeouts, memory limits, truncation.

These verify that the *enforced* resource limits (thread-based interrupt for
timeouts, DuckDB ``memory_limit`` for memory, ``max_rows`` for result size)
actually bound pathological queries — not merely that validation rejects
dangerous syntax.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from computation_helpers import build_data_dir
from qwen_research.computation.analytics import DuckDBBackend
from qwen_research.computation.datasets import DatasetResolver, ResolvedDataset
from qwen_research.computation.models import DatasetReference
from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.domain.errors import ExecutionTimeoutError, ResourceLimitError


def _resolver(data: Path) -> DatasetResolver:
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="data", path=str(data), read_only=True, recursive=True),)
    )
    return DatasetResolver(config)


def _write_rows(data: Path, name: str, n: int) -> ResolvedDataset:
    (data / name).write_text("i\n" + "\n".join(str(i) for i in range(n)) + "\n")
    return _resolver(data).resolve(DatasetReference(root_id="data", relative_path=name))


def test_query_timeout_enforced(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolved = _write_rows(data, "big.csv", 2000)
    backend = DuckDBBackend()
    # A 3-way cross join of a 2000-row table is slow (~1.5s); a 0.3s limit
    # must interrupt it and raise a real timeout.
    with pytest.raises(ExecutionTimeoutError):
        backend.run_query(
            [resolved], "SELECT count(*) FROM t0 a, t0 b, t0 c", {},
            max_rows=100, max_output_bytes=1024 * 1024, time_limit_seconds=0.3,
        )


def test_query_memory_limit_enforced(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolved = _write_rows(data, "big.csv", 5000)
    backend = DuckDBBackend()
    # Building a 25M-entry distinct hash set (5000^2) exceeds 64 MiB and must
    # raise a ResourceLimitError rather than a raw DuckDB exception.
    with pytest.raises(ResourceLimitError):
        backend.run_query(
            [resolved], "SELECT count(DISTINCT a.i * 100000 + b.i) FROM t0 a, t0 b", {},
            max_rows=10, max_output_bytes=1024 * 1024,
            max_memory_bytes=64 * 1024 * 1024,
        )


def test_large_result_truncated(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolved = _write_rows(data, "big.csv", 1000)
    backend = DuckDBBackend()
    # 1000^2 = 1,000,000 rows; max_rows bounds the returned rows.
    table = backend.run_query(
        [resolved], "SELECT * FROM t0 a, t0 b", {},
        max_rows=50, max_output_bytes=1024 * 1024,
    )
    assert table.truncated is True
    assert len(table.rows) == 50


def test_output_bytes_limit_enforced(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolved = _write_rows(data, "big.csv", 5000)
    backend = DuckDBBackend()
    with pytest.raises(ResourceLimitError):
        backend.run_query(
            [resolved], "SELECT * FROM t0", {},
            max_rows=100_000, max_output_bytes=128,
        )


def test_structured_aggregate_respects_limits(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolved = _write_rows(data, "big.csv", 2000)
    backend = DuckDBBackend()
    # A full cross-join count via a structured path is still bounded.
    with pytest.raises(ExecutionTimeoutError):
        backend.run_query(
            [resolved], "SELECT sum(a.i) FROM t0 a, t0 b, t0 c", {},
            max_rows=10, max_output_bytes=1024 * 1024, time_limit_seconds=0.3,
        )
