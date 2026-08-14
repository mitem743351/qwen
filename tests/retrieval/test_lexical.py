"""Lexical retrieval tests: keyword search, ranking, filters, provenance."""

from __future__ import annotations

from pathlib import Path

from corpus_helpers import index_fixture
from qwen_research.retrieval.evidence import to_evidence
from qwen_research.retrieval.models import SearchOptions


def test_exact_keyword_returns_results(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("surface code")
    assert result.returned_count >= 1
    assert any("surface code" in c.text.lower() for c in result.chunks)


def test_multiple_results_ranked(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("error correction", SearchOptions(limit=5))
    assert result.returned_count >= 1
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)


def test_result_provenance(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("quantum")
    for chunk in result.chunks:
        assert chunk.chunk_id
        assert chunk.document_id
        assert chunk.source_id
        assert chunk.relative_path or chunk.path
        assert chunk.text


def test_filter_by_document_type(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search(
        "surface", SearchOptions(limit=20, document_types=("text/markdown",))
    )
    assert result.returned_count >= 1
    for chunk in result.chunks:
        assert chunk.media_type == "text/markdown"


def test_limit_respected(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("the", SearchOptions(limit=2))
    assert result.returned_count <= 2


def test_minimum_score_filters(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    all_results = retriever.search("correction", SearchOptions(limit=20))
    if all_results.returned_count >= 2:
        top = all_results.chunks[0].score
        filtered = retriever.search(
            "correction", SearchOptions(limit=20, minimum_score=top)
        )
        assert filtered.returned_count <= all_results.returned_count


def test_evidence_packaging(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("quantum error")
    assert result.chunks
    evidence = to_evidence(result.chunks[0])
    assert evidence.source_id
    assert evidence.excerpt
    assert evidence.location
    assert evidence.relevance is not None
    assert "document_id" in evidence.metadata


def test_get_document(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    result = retriever.search("surface code")
    doc_id = result.chunks[0].document_id
    view = retriever.get_document(doc_id)
    assert view is not None
    assert view.document_id == doc_id
    assert view.relative_path
    assert view.media_type


def test_get_document_missing_returns_none(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    assert retriever.get_document("doc_nonexistent") is None


def test_stats_and_status(tmp_path: Path) -> None:
    index, _, _, retriever, _ = index_fixture(tmp_path)
    stats = retriever.stats()
    assert stats.documents >= 1
    assert stats.chunks >= 1
    status = retriever.status()
    assert status.documents == stats.documents
