"""Shared helpers for Phase 3 corpus/indexing/retrieval tests.

The fixture corpus is **copied** into ``tmp_path`` for every test so that tests
which mutate files (modify, delete) never corrupt the committed fixtures.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.indexing.manager import IndexManager, IndexReport
from qwen_research.indexing.sqlite import SqliteCorpusIndex
from qwen_research.retrieval.lexical import LexicalRetriever

FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


def copy_fixture_corpus(tmp_path: Path) -> Path:
    """Copy the fixture corpus into *tmp_path* and return the new path."""
    dest = tmp_path / "corpus"
    shutil.copytree(FIXTURE_CORPUS, dest)
    return dest


def fixture_config(
    *,
    root_id: str = "fixtures",
    corpus_path: Path | None = None,
    extra_roots: tuple[CorpusRoot, ...] = (),
) -> CorpusConfig:
    path = str(corpus_path or FIXTURE_CORPUS)
    return CorpusConfig(
        roots=(
            CorpusRoot(
                root_id=root_id,
                path=path,
                read_only=True,
                recursive=True,
            ),
        )
        + extra_roots,
    )


def build_index(tmp_path: Path, config: CorpusConfig) -> tuple[SqliteCorpusIndex, IndexManager]:
    index = SqliteCorpusIndex(tmp_path / "corpus.db")
    manager = IndexManager(config, index)
    manager.initialize()
    return index, manager


def index_fixture(
    tmp_path: Path,
) -> tuple[SqliteCorpusIndex, IndexManager, IndexReport, LexicalRetriever, Path]:
    """Index a fresh copy of the fixture corpus; return index, manager, report,
    retriever, and the copied corpus path (for mutation tests)."""
    corpus_path = copy_fixture_corpus(tmp_path)
    config = fixture_config(corpus_path=corpus_path)
    index, manager = build_index(tmp_path, config)
    report = manager.index_all()
    retriever = LexicalRetriever(index)
    return index, manager, report, retriever, corpus_path
