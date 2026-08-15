"""Helpers for Phase 6 deterministic-computation tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.computation.datasets import DatasetResolver
from qwen_research.computation.models import DatasetReference
from qwen_research.computation.service import ComputationService
from qwen_research.computation.store import ComputationStore
from qwen_research.corpus.config import CorpusConfig, CorpusRoot


def build_data_dir(tmp_path: Path) -> Path:
    """Create a small corpus of datasets (csv/json/parquet/sqlite)."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "numbers.csv").write_text("group,value\nA,1.0\nA,2.0\nB,3.0\nB,5.0\nB,7.0\n")
    (data / "people.json").write_text(
        '[{"name":"alice","age":30,"score":1.5},'
        '{"name":"bob","age":25,"score":2.5},'
        '{"name":"carol","age":35,"score":3.5}]'
    )
    (data / "wide.csv").write_text("a,b\n1,2\n3,4\n5,6\n")
    _write_parquet(data / "sample.parquet")
    _write_sqlite(data / "sample.sqlite")
    return data


def _write_parquet(path: Path) -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1, 'x'), (2, 'y'), (3, 'z')) t(a, b)")
    con.execute(f"COPY t TO '{path}' (FORMAT PARQUET)")


def _write_sqlite(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE metrics (k INTEGER, v REAL)")
    con.executemany("INSERT INTO metrics VALUES (?, ?)", [(1, 2.0), (2, 4.0), (3, 6.0)])
    con.commit()
    con.close()


def build_service(
    tmp_path: Path,
    *,
    enable_python_execution: bool = False,
) -> tuple[ComputationService, ComputationStore, DatasetResolver, ArtifactStore, Path]:
    """Build a ComputationService over a sample dataset corpus."""
    data = build_data_dir(tmp_path)
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="data", path=str(data), read_only=True, recursive=True),)
    )
    store = ComputationStore(tmp_path / "computation.db")
    store.initialize()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    resolver = DatasetResolver(config, artifacts_root=str(tmp_path / "artifacts"))
    service = ComputationService(
        store, resolver, artifacts=artifacts,
        enable_python_execution=enable_python_execution,
    )
    return service, store, resolver, artifacts, data


def ref(data: Path, name: str) -> DatasetReference:
    return DatasetReference(root_id="data", relative_path=name)
