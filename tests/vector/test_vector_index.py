"""Vector index tests: upsert/delete/search/stale/rebuild/persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from qwen_research.vector.interface import VectorRecord
from qwen_research.vector.sqlite import SqliteVectorIndex


def _record(chunk_id: str, vector: tuple[float, ...], *, version: str = "1") -> VectorRecord:
    return VectorRecord(
        chunk_id=chunk_id,
        model="hash-ngram-v1",
        version=version,
        dimension=len(vector),
        vector=vector,
        text_hash=hashlib.sha256(chunk_id.encode()).hexdigest(),
    )


def _index(tmp_path: Path) -> SqliteVectorIndex:
    idx = SqliteVectorIndex(tmp_path / "v.db")
    idx.initialize()
    return idx


def test_upsert_and_search(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert(
        [
            _record("c1", (1.0, 0.0, 0.0)),
            _record("c2", (0.0, 1.0, 0.0)),
            _record("c3", (0.0, 0.0, 1.0)),
        ]
    )
    hits = idx.search((1.0, 0.0, 0.0), model="hash-ngram-v1", version="1", limit=2)
    assert hits[0].chunk_id == "c1"


def test_delete_removes(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert([_record("c1", (1.0, 0.0))])
    assert idx.delete(["c1"]) == 1
    assert idx.get("c1") is None


def test_stale_model_detection(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert([_record("c1", (1.0, 0.0), version="1")])
    idx.upsert([_record("c1", (0.5, 0.5), version="2")])
    rec = idx.get("c1")
    assert rec is not None
    assert rec.version == "2"
    assert rec.vector == (0.5, 0.5)


def test_search_scopes_by_model_version(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert([_record("c1", (1.0, 0.0), version="1")])
    hits = idx.search((1.0, 0.0), model="hash-ngram-v1", version="2", limit=5)
    assert hits == []


def test_rebuild_clears(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert([_record("c1", (1.0, 0.0))])
    idx.rebuild()
    assert idx.stats()["vectors"] == 0


def test_persistence_across_restart(tmp_path: Path) -> None:
    idx = SqliteVectorIndex(tmp_path / "v.db")
    idx.initialize()
    idx.upsert([_record("c1", (1.0, 0.0))])
    idx.close()

    idx2 = SqliteVectorIndex(tmp_path / "v.db")
    idx2.initialize()
    assert idx2.get("c1") is not None


def test_cosine_similarity_bounds(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    idx.upsert([_record("c1", (1.0, 2.0, 3.0))])
    hits = idx.search((1.0, 2.0, 3.0), model="hash-ngram-v1", version="1", limit=1)
    assert abs(hits[0].score - 1.0) < 1e-9
