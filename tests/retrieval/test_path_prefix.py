"""Regression: path-prefix filter boundary + literal (non-wildcard) semantics.

A ``path_prefix`` filter must match at a path-component boundary (the prefix
itself, or ``prefix/...``) and must treat ``%``/``_`` in the prefix literally,
never as SQL LIKE wildcards.
"""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.indexing.manager import IndexManager
from qwen_research.indexing.sqlite import SqliteCorpusIndex
from qwen_research.retrieval.lexical import LexicalRetriever
from qwen_research.retrieval.models import SearchOptions


def _build(tmp_path: Path) -> LexicalRetriever:
    root = tmp_path / "corpus"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.txt").write_text("alpha topic marker")
    (root / "notes" / "b.txt").write_text("beta topic marker")
    (root / "notes2.txt").write_text("should not match notes prefix")
    (root / "notes_extra").mkdir()
    (root / "notes_extra" / "c.txt").write_text("underscore marker")
    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(root)),))
    index = SqliteCorpusIndex(tmp_path / "c.db")
    IndexManager(config, index).index_all()
    return LexicalRetriever(index)


def test_prefix_matches_children_but_not_notes2(tmp_path: Path) -> None:
    retriever = _build(tmp_path)
    result = retriever.search(
        "topic", SearchOptions(limit=20, path_prefix="notes")
    )
    paths = {c.relative_path for c in result.chunks}
    assert "notes/a.txt" in paths
    assert "notes/b.txt" in paths
    # Boundary: "notes2.txt" and "notes_extra/c.txt" are NOT under "notes/".
    assert "notes2.txt" not in paths
    assert "notes_extra/c.txt" not in paths


def test_prefix_treats_percent_literally(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir(parents=True)
    (root / "a%c").mkdir()
    (root / "a%c" / "x.txt").write_text("marker")
    (root / "abc").mkdir()
    (root / "abc" / "y.txt").write_text("marker")

    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(root)),))
    index = SqliteCorpusIndex(tmp_path / "c2.db")
    IndexManager(config, index).index_all()
    retriever = LexicalRetriever(index)

    result = retriever.search(
        "marker", SearchOptions(limit=20, path_prefix="a%c")
    )
    paths = {c.relative_path for c in result.chunks}
    # '%' is literal: only the directory literally named "a%c" matches.
    assert "a%c/x.txt" in paths
    assert "abc/y.txt" not in paths


def test_prefix_treats_underscore_literally(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir(parents=True)
    (root / "a_c").mkdir()
    (root / "a_c" / "x.txt").write_text("marker")
    (root / "abc").mkdir()
    (root / "abc" / "y.txt").write_text("marker")

    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(root)),))
    index = SqliteCorpusIndex(tmp_path / "c3.db")
    IndexManager(config, index).index_all()
    retriever = LexicalRetriever(index)

    result = retriever.search(
        "marker", SearchOptions(limit=20, path_prefix="a_c")
    )
    paths = {c.relative_path for c in result.chunks}
    # '_' is literal: only the directory literally named "a_c" matches.
    assert "a_c/x.txt" in paths
    assert "abc/y.txt" not in paths


def test_trailing_slash_is_normalized(tmp_path: Path) -> None:
    retriever = _build(tmp_path)
    result = retriever.search(
        "topic", SearchOptions(limit=20, path_prefix="notes/")
    )
    paths = {c.relative_path for c in result.chunks}
    assert "notes/a.txt" in paths
    assert "notes2.txt" not in paths
