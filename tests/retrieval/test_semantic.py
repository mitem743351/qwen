"""Semantic retrieval tests (hashing embedder + brute-force vector index)."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_hybrid_stack
from qwen_research.retrieval.models import RetrievalMode, SearchOptions


def test_semantic_finds_related_document(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["semantic"].search(
        "methods for reducing quantum error rates", SearchOptions(limit=5)
    )
    assert result.mode == RetrievalMode.SEMANTIC.value
    paths = [c.relative_path for c in result.chunks]
    # The related quantum documents rank above the unrelated pottery document.
    assert paths.index("decoherence.txt") < paths.index("pottery.txt")
    assert "decoherence.txt" in paths


def test_semantic_score_recorded(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["semantic"].search("quantum error", SearchOptions(limit=5))
    for chunk in result.chunks:
        assert chunk.semantic_score is not None
        assert chunk.lexical_score is None


def test_empty_query_returns_nothing(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["semantic"].search("   ", SearchOptions(limit=5))
    assert result.returned_count == 0


def test_incremental_embedding_is_idempotent(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    # The helper already ran one sync; a second sync changes nothing.
    assert stack["embed_report"].embedded == 3
    second = stack["embed_manager"].sync()
    assert second.embedded == 0
    assert second.skipped == 3


def test_changed_chunk_is_reembedded(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    corpus = stack["corpus"]
    (corpus / "surface_code.txt").write_text(
        "A completely different topic about machine learning gradient descent.\n"
    )
    stack["manager"].index_all()
    report = stack["embed_manager"].sync()
    assert report.embedded >= 1
