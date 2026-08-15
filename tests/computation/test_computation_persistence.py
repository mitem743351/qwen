"""Computation persistence and restart tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from computation_helpers import build_data_dir, ref
from qwen_research.computation.datasets import DatasetResolver
from qwen_research.computation.models import ComputationOperation
from qwen_research.computation.service import ComputationService
from qwen_research.computation.store import ComputationStore
from qwen_research.corpus.config import CorpusConfig, CorpusRoot


def test_full_restart_persistence(tmp_path: Path) -> None:
    data = build_data_dir(tmp_path)
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="data", path=str(data), read_only=True, recursive=True),)
    )
    db = tmp_path / "computation.db"

    # First process: run a computation.
    store = ComputationStore(db)
    store.initialize()
    service = ComputationService(store, DatasetResolver(config))
    result = service.run_analysis(
        "p", (ref(data, "numbers.csv"),), ComputationOperation.COUNT
    )
    computation_id = result.computation_id
    store.close()

    # Second process: reopen and read the result.
    store2 = ComputationStore(db)
    store2.initialize()
    service2 = ComputationService(store2, DatasetResolver(config))
    loaded = service2.get_computation_result("p", computation_id)
    assert loaded.status is result.status
    assert loaded.value == result.value
    assert loaded.provenance == result.provenance


def test_schema_version(tmp_path: Path) -> None:
    store = ComputationStore(tmp_path / "c.db")
    store.initialize()
    conn = sqlite3.connect(tmp_path / "c.db")
    version = conn.execute(
        "SELECT value FROM computation_meta WHERE key='schema_version'"
    ).fetchone()[0]
    conn.close()
    assert version == "1"
