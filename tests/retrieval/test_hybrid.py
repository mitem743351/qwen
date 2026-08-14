"""Hybrid retrieval tests: fusion, diversity, fallback, determinism, filters."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_hybrid_stack
from qwen_research.retrieval.models import RetrievalMode, SearchOptions


def test_lexical_only_mode(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search(
        "surface code", SearchOptions(limit=5, mode=RetrievalMode.LEXICAL)
    )
    assert result.mode == RetrievalMode.LEXICAL.value
    for chunk in result.chunks:
        assert chunk.retrieval_mode == RetrievalMode.LEXICAL.value


def test_semantic_only_mode(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search(
        "suppressing decoherence", SearchOptions(limit=5, mode=RetrievalMode.SEMANTIC)
    )
    assert result.mode == RetrievalMode.SEMANTIC.value


def test_hybrid_mode_records_components(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search(
        "methods for reducing quantum error rates", SearchOptions(limit=5)
    )
    assert result.mode == RetrievalMode.HYBRID.value
    assert result.semantic_hits is not None and result.semantic_hits >= 1
    for chunk in result.chunks:
        assert chunk.retrieval_mode == RetrievalMode.HYBRID.value
        assert chunk.fusion_score is not None


def test_hybrid_deterministic_ordering(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    a = stack["hybrid"].search("quantum error rates", SearchOptions(limit=5))
    b = stack["hybrid"].search("quantum error rates", SearchOptions(limit=5))
    assert [c.chunk_id for c in a.chunks] == [c.chunk_id for c in b.chunks]


def test_semantic_fallback_when_no_lexical_hits(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    # A query with no exact token matches still yields semantic results.
    result = stack["hybrid"].search("diminishing quantum fault frequency", SearchOptions(limit=5))
    assert result.returned_count >= 1
    assert result.lexical_hits == 0
    assert result.semantic_hits >= 1


def test_document_diversity_limit(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search(
        "quantum error", SearchOptions(limit=20, max_chunks_per_document=1)
    )
    doc_counts: dict[str, int] = {}
    for chunk in result.chunks:
        doc_counts[chunk.document_id] = doc_counts.get(chunk.document_id, 0) + 1
    assert all(count <= 1 for count in doc_counts.values())


def test_filters_applied(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search(
        "quantum error",
        SearchOptions(limit=20, document_types=("text/plain",)),
    )
    assert result.returned_count >= 1
    for chunk in result.chunks:
        assert chunk.media_type == "text/plain"
