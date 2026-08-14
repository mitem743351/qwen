"""Regression: FTS5 query escaping.

User query text must be searched literally — an embedded ``"`` or FTS5 operator
(``AND``/``OR``/``NEAR``/``*``/``^``/parens) must never be interpreted as FTS5
syntax or raise a parse error.
"""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.indexing.manager import IndexManager
from qwen_research.indexing.sqlite import SqliteCorpusIndex, _fts_query
from qwen_research.retrieval.lexical import LexicalRetriever
from qwen_research.retrieval.models import SearchOptions


def _index_doc(tmp_path: Path, text: str) -> LexicalRetriever:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "doc.txt").write_text(text)
    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(root)),))
    index = SqliteCorpusIndex(tmp_path / "c.db")
    IndexManager(config, index).index_all()
    return LexicalRetriever(index)


def test_fts_query_escapes_quotes() -> None:
    # The embedded quote is doubled inside the phrase so it stays literal.
    assert _fts_query('he said "hello"') == '"he" "said" """hello"""'


def test_fts_query_escapes_operator_tokens() -> None:
    # AND/OR/NEAR/* become literal phrase tokens, not FTS syntax.
    q = _fts_query("AND OR NEAR * (foo)")
    assert q == '"AND" "OR" "NEAR" "*" "(foo)"'


def test_search_with_embedded_quote_does_not_raise(tmp_path: Path) -> None:
    retriever = _index_doc(tmp_path, 'the operator "NEAR" is important')
    result = retriever.search('"NEAR"', SearchOptions(limit=5))
    assert result.returned_count >= 1


def test_search_with_operators_is_literal(tmp_path: Path) -> None:
    # A query consisting of FTS operator words is searched literally, not
    # treated as a boolean expression.
    retriever = _index_doc(tmp_path, "OR is a boolean operator word")
    result = retriever.search("OR", SearchOptions(limit=5))
    assert result.returned_count >= 1


def test_search_with_wildcard_character_does_not_raise(tmp_path: Path) -> None:
    retriever = _index_doc(tmp_path, "asterisk star wildcard")
    result = retriever.search("ast*", SearchOptions(limit=5))
    # No exception; the literal phrase "ast*" simply matches nothing.
    assert result.returned_count >= 0
