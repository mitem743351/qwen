"""DuckDB backend tests: formats, SQL safety, parameterization, escapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from computation_helpers import build_data_dir
from qwen_research.computation.analytics import DuckDBBackend, validate_identifier, validate_sql
from qwen_research.computation.datasets import DatasetResolver, ResolvedDataset
from qwen_research.computation.models import DatasetReference
from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.domain.errors import PathSecurityError, QueryValidationError


def _resolver(data: Path) -> DatasetResolver:
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="data", path=str(data), read_only=True, recursive=True),)
    )
    return DatasetResolver(config)


def _r(data: Path, name: str) -> ResolvedDataset:
    return _resolver(data).resolve(DatasetReference(root_id="data", relative_path=name))


def test_csv_aggregate(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "numbers.csv")
    table = backend.aggregate([resolved], "value", "mean", max_rows=100)
    assert table.rows[0][0] == 3.6


def test_csv_group_by(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "numbers.csv")
    table = backend.group([resolved], "group", "value", "sum", max_rows=100)
    assert table.rows == [("A", 3.0), ("B", 15.0)]


def test_json_profile(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "people.json")
    profile = backend.describe_dataset(resolved, max_rows=100)
    assert profile.row_count == 3
    assert profile.column_count == 3


def test_parquet_read(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "sample.parquet")
    table = backend.count([resolved], max_rows=100)
    assert table.rows[0][0] == 3


def test_sqlite_read(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "sample.sqlite")
    table = backend.aggregate([resolved], "v", "sum", max_rows=100)
    assert table.rows[0][0] == 12.0


def test_join(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolver = _resolver(data)
    left = resolver.resolve(DatasetReference(root_id="data", relative_path="wide.csv"))
    right = resolver.resolve(DatasetReference(root_id="data", relative_path="wide.csv"))
    table = backend.join([left, right], "a", "a", max_rows=100)
    assert table.row_count == 3


def test_parameterized_query(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    backend = DuckDBBackend()
    resolved = _r(data, "numbers.csv")
    table = backend.run_query(
        [resolved], "SELECT * FROM t0 WHERE value >= :min_v", {"min_v": 3.0},
        max_rows=100, max_output_bytes=1024 * 1024,
    )
    assert table.row_count == 3


@pytest.mark.parametrize(
    "query",
    [
        "COPY t0 TO '/tmp/out.csv'",
        "ATTACH '/tmp/x.db' AS other",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "PRAGMA database_list",
    ],
)
def test_sql_escape_attempts_rejected(query: str) -> None:
    with pytest.raises(QueryValidationError):
        validate_sql(query)


def test_multiple_statements_rejected() -> None:
    with pytest.raises(QueryValidationError):
        validate_sql("SELECT 1; SELECT 2")


def test_invalid_identifier_rejected() -> None:
    with pytest.raises(QueryValidationError):
        validate_identifier("value; DROP TABLE t")


def test_read_outside_corpus_rejected(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolver = _resolver(data)

    # A reference pointing outside the root (../ escape) is rejected by the
    # corpus security layer.
    with pytest.raises(PathSecurityError):
        resolver.resolve(DatasetReference(root_id="data", relative_path="../secret.csv"))


def test_artifact_dataset_input_reserved(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    resolver = _resolver(data)
    from qwen_research.domain.errors import DatasetError

    with pytest.raises(DatasetError, match="reserved"):
        resolver.resolve(DatasetReference(artifact_id="artifact_123"))
