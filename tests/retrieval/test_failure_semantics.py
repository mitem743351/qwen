"""Regression: retrieval failure semantics.

Expected backend outages must produce controlled fallback with explicit
degradation; unexpected programming failures must propagate and are never
silently converted into zero hits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phase4_helpers import build_hybrid_stack
from qwen_research.domain.errors import (
    RetrievalBackendUnavailable,
    SemanticRetrievalUnavailable,
)
from qwen_research.retrieval.hybrid import HybridRetriever
from qwen_research.retrieval.models import RetrievalMode, SearchOptions, SearchResult


class _UnavailableSemantic:
    """A semantic retriever that is legitimately down (backend outage)."""

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        raise SemanticRetrievalUnavailable("vector index missing")


class _BrokenSemantic:
    """A semantic retriever with a programming defect (unexpected)."""

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        raise TypeError("unexpected programming error in semantic retriever")


class _BrokenLexical:
    """A lexical retriever with a programming defect (unexpected)."""

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        raise RuntimeError("unexpected programming error in lexical retriever")


class _UnavailableLexical:
    """A lexical retriever that is legitimately down (backend outage)."""

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        raise RetrievalBackendUnavailable("fts index corrupt")


def _hybrid(lexical: object, semantic: object) -> HybridRetriever:
    return HybridRetriever(lexical, semantic, lexical_k=10, semantic_k=10, final_k=5)  # type: ignore[arg-type]


def test_successful_hybrid_is_not_degraded(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    result = stack["hybrid"].search("quantum error", SearchOptions(limit=5))
    assert result.mode == RetrievalMode.HYBRID.value
    assert result.degraded is False
    assert result.degradation_reason is None
    assert result.lexical_available is True
    assert result.semantic_available is True


def test_semantic_unavailable_falls_back_to_lexical(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(stack["lexical"], _UnavailableSemantic())
    result = hybrid.search("surface code", SearchOptions(limit=5))
    assert result.degraded is True
    assert result.degradation_reason == "semantic_backend_unavailable"
    assert result.semantic_available is False
    assert result.lexical_available is True
    # Lexical fallback still produced results (not an empty success).
    assert result.returned_count >= 1


def test_lexical_unavailable_falls_back_to_semantic(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(_UnavailableLexical(), stack["semantic"])
    result = hybrid.search("methods for reducing quantum error rates", SearchOptions(limit=5))
    assert result.degraded is True
    assert result.degradation_reason == "lexical_backend_unavailable"
    assert result.lexical_available is False
    assert result.semantic_available is True
    assert result.returned_count >= 1


def test_both_unavailable_raises(tmp_path: Path) -> None:
    hybrid = _hybrid(_UnavailableLexical(), _UnavailableSemantic())
    with pytest.raises(RetrievalBackendUnavailable):
        hybrid.search("anything", SearchOptions(limit=5))


def test_unexpected_semantic_exception_propagates(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(stack["lexical"], _BrokenSemantic())
    with pytest.raises(TypeError):
        hybrid.search("surface code", SearchOptions(limit=5))


def test_unexpected_lexical_exception_propagates(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(_BrokenLexical(), stack["semantic"])
    with pytest.raises(RuntimeError):
        hybrid.search("surface code", SearchOptions(limit=5))


def test_semantic_failure_is_not_hidden_as_zero_hits(tmp_path: Path) -> None:
    # A programming defect in the semantic retriever must NOT be reported as
    # "0 semantic hits" in a successful-looking result; it must propagate.
    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(stack["lexical"], _BrokenSemantic())
    with pytest.raises(TypeError):
        hybrid.search("surface code", SearchOptions(limit=5))


def test_no_semantic_hits_is_not_degraded(tmp_path: Path) -> None:
    # Semantic backend is available but returns nothing: normal (non-degraded).
    class _EmptySemantic:
        def search(
            self, query: str, options: SearchOptions | None = None
        ) -> SearchResult:
            return SearchResult((), query, 0, 0, 0.0, RetrievalMode.SEMANTIC.value)

    stack = build_hybrid_stack(tmp_path)
    hybrid = _hybrid(stack["lexical"], _EmptySemantic())
    result = hybrid.search("surface code", SearchOptions(limit=5))
    assert result.degraded is False
    assert result.semantic_hits == 0
    assert result.returned_count >= 1
