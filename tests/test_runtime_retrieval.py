"""Research Runtime retrieval integration (no MCP, no Qwen, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus_helpers import index_fixture
from qwen_research.domain.errors import DocumentNotFoundError, UnsupportedOperationError
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.retrieval.models import SearchOptions


def test_search_corpus_without_retriever_is_unsupported() -> None:
    runtime = InMemoryResearchRuntime()
    with pytest.raises(UnsupportedOperationError):
        runtime.search_corpus("quantum")


def test_search_corpus_returns_evidence(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=retriever)
    result = runtime.search_corpus("surface code")
    assert result.returned_count >= 1
    assert result.chunks[0].document_id


def test_search_corpus_options(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=retriever)
    result = runtime.search_corpus(
        "the", SearchOptions(limit=2, document_types=("text/markdown",))
    )
    assert result.returned_count <= 2
    for chunk in result.chunks:
        assert chunk.media_type == "text/markdown"


def test_get_source_returns_document(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=retriever)
    doc_id = runtime.search_corpus("surface code").chunks[0].document_id
    view = runtime.get_source(doc_id)
    assert view.document_id == doc_id
    assert view.relative_path
    assert view.media_type


def test_get_source_missing_raises(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=retriever)
    with pytest.raises(DocumentNotFoundError):
        runtime.get_source("doc_nonexistent")


def test_get_source_without_retriever_is_unsupported() -> None:
    runtime = InMemoryResearchRuntime()
    with pytest.raises(UnsupportedOperationError):
        runtime.get_source("doc_1")
