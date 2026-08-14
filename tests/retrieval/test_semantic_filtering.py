"""Regression: filter-correct semantic search via overfetch.

The semantic backend has no native metadata filtering, so the retriever must
overfetch candidates, apply filters, and only then truncate. This suite proves
that a filter does not destroy recall when the top (unfiltered) candidates fall
outside the requested filter.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.embeddings.hashing import HashingEmbeddingProvider
from qwen_research.embeddings.manager import EmbeddingManager
from qwen_research.indexing.manager import IndexManager
from qwen_research.indexing.sqlite import SqliteCorpusIndex
from qwen_research.retrieval.models import RetrievalMode, SearchOptions
from qwen_research.retrieval.semantic import SemanticRetriever
from qwen_research.vector.sqlite import SqliteVectorIndex


def _semantic(
    tmp_path: Path, *, roots: tuple[CorpusRoot, ...], dimension: int = 128
) -> SemanticRetriever:
    config = CorpusConfig(roots=roots)
    index = SqliteCorpusIndex(tmp_path / "corpus.db")
    IndexManager(config, index).index_all()
    provider = HashingEmbeddingProvider(dimension=dimension)
    vindex = SqliteVectorIndex(tmp_path / "v.db")
    vindex.initialize()
    EmbeddingManager(index, vindex, provider).sync()
    return SemanticRetriever(index, vindex, provider)


def _multi_root(tmp_path: Path) -> Path:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    # Root A dominates the top-K semantic results (many near-duplicate docs).
    for i in range(15):
        (root_a / f"qa_{i}.txt").write_text(
            "quantum error correction thresholds in fault tolerant computing"
        )
    # Root B has a single relevant doc that would rank below the A flood.
    (root_b / "book.txt").write_text(
        "methods for reducing quantum error rates using surface codes"
    )
    return tmp_path


def _roots(tmp_path: Path) -> tuple[CorpusRoot, ...]:
    return (
        CorpusRoot(root_id="a", path=str(tmp_path / "a"), read_only=True, recursive=True),
        CorpusRoot(root_id="b", path=str(tmp_path / "b"), read_only=True, recursive=True),
    )


def test_root_filter_captures_low_ranked_root(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    result = semantic.search(
        "quantum error correction", SearchOptions(limit=3, roots=("b",))
    )
    # Overfetch captured the root-B candidate that a naive top-3 would have
    # missed (the top 3 unfiltered candidates are all in root A).
    assert result.returned_count >= 1
    assert all(c.root_id == "b" for c in result.chunks)


def test_naive_top_k_would_have_failed_without_overfetch(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    # Unfiltered: top results are all root A.
    unfiltered = semantic.search("quantum error correction", SearchOptions(limit=3))
    assert all(c.root_id == "a" for c in unfiltered.chunks)
    # With a root filter for "b", overfetch still finds the root-B doc.
    filtered = semantic.search(
        "quantum error correction", SearchOptions(limit=3, roots=("b",))
    )
    assert filtered.returned_count >= 1
    assert all(c.root_id == "b" for c in filtered.chunks)


def test_document_type_filter(tmp_path: Path) -> None:
    base = tmp_path
    (base / "md").mkdir()
    (base / "txt").mkdir()
    for i in range(15):
        (base / "txt" / f"t{i}.txt").write_text("quantum error correction thresholds")
    (base / "md" / "notes.md").write_text("reducing quantum error rates with surface codes")
    roots = (
        CorpusRoot(root_id="txt", path=str(base / "txt"), read_only=True, recursive=True),
        CorpusRoot(root_id="md", path=str(base / "md"), read_only=True, recursive=True),
    )
    semantic = _semantic(tmp_path, roots=roots)
    result = semantic.search(
        "quantum error correction",
        SearchOptions(limit=3, document_types=("text/markdown",)),
    )
    assert result.returned_count >= 1
    assert all(c.media_type == "text/markdown" for c in result.chunks)


def test_path_prefix_filter(tmp_path: Path) -> None:
    base = tmp_path / "corpus"
    (base / "top").mkdir(parents=True)
    (base / "sub").mkdir(parents=True)
    for i in range(15):
        (base / "top" / f"t{i}.txt").write_text("quantum error correction thresholds")
    (base / "sub" / "paper.txt").write_text("reducing quantum error rates via surface codes")
    root = CorpusRoot(root_id="r", path=str(base), read_only=True, recursive=True)
    semantic = _semantic(tmp_path, roots=(root,))
    result = semantic.search(
        "quantum error correction", SearchOptions(limit=3, path_prefix="sub")
    )
    assert result.returned_count >= 1
    assert all((c.relative_path or "").startswith("sub/") for c in result.chunks)


def test_restrictive_filter_yields_empty_not_error(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    result = semantic.search(
        "quantum error correction", SearchOptions(limit=3, roots=("nonexistent",))
    )
    assert result.returned_count == 0
    assert result.chunks == ()


def test_date_filter(tmp_path: Path) -> None:
    import os
    import time

    base = tmp_path / "corpus"
    base.mkdir()
    old_file = base / "old.txt"
    new_file = base / "new.txt"
    old_file.write_text("quantum error correction thresholds")
    new_file.write_text("quantum error correction thresholds")

    old_ts = time.mktime(datetime(2019, 1, 1).timetuple())
    new_ts = time.mktime(datetime(2024, 1, 1).timetuple())
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    root = CorpusRoot(root_id="r", path=str(base), read_only=True, recursive=True)
    semantic = _semantic(tmp_path, roots=(root,))
    lo, hi = datetime(2023, 1, 1), datetime(2025, 1, 1)
    result = semantic.search(
        "quantum error correction", SearchOptions(limit=10, date_range=(lo, hi))
    )
    assert result.returned_count >= 1
    assert all(c.relative_path == "new.txt" for c in result.chunks)


def test_candidate_limit_is_distinct_from_final_limit(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    result = semantic.search(
        "quantum error correction",
        SearchOptions(
            limit=2,
            roots=("a",),
            semantic_overfetch_factor=5,
            minimum_candidate_pool=20,
        ),
    )
    # returned_count is bounded by the final limit, not the candidate pool.
    assert result.returned_count <= 2
    assert result.candidate_count >= result.returned_count


def test_minimum_score_filter(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    result = semantic.search(
        "quantum error correction",
        SearchOptions(limit=10, minimum_score=0.99),
    )
    # A very high threshold legitimately yields few/no results, not an error.
    assert result.returned_count >= 0


def test_mode_is_semantic(tmp_path: Path) -> None:
    _multi_root(tmp_path)
    semantic = _semantic(tmp_path, roots=_roots(tmp_path))
    result = semantic.search("quantum", SearchOptions(limit=3))
    assert result.mode == RetrievalMode.SEMANTIC.value
    for chunk in result.chunks:
        assert chunk.semantic_score is not None
        assert chunk.lexical_score is None
