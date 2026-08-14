"""Helpers for Phase 4 (semantic/hybrid retrieval + memory) tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.embeddings.hashing import HashingEmbeddingProvider
from qwen_research.embeddings.manager import EmbeddingManager
from qwen_research.indexing.manager import IndexManager
from qwen_research.indexing.sqlite import SqliteCorpusIndex
from qwen_research.memory.service import MemoryService
from qwen_research.memory.sqlite import SqliteMemoryStore
from qwen_research.retrieval.hybrid import HybridRetriever
from qwen_research.retrieval.lexical import LexicalRetriever
from qwen_research.retrieval.semantic import SemanticRetriever
from qwen_research.vector.sqlite import SqliteVectorIndex

FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"
SEMANTIC_CORPUS = Path(__file__).resolve().parent / "fixtures" / "semantic"


def copy_semantic_corpus(tmp_path: Path) -> Path:
    dest = tmp_path / "semantic"
    shutil.copytree(SEMANTIC_CORPUS, dest)
    return dest


def config_for(corpus_path: Path, *, root_id: str = "semantic") -> CorpusConfig:
    return CorpusConfig(
        roots=(CorpusRoot(root_id=root_id, path=str(corpus_path), read_only=True, recursive=True),)
    )


def build_hybrid_stack(
    tmp_path: Path,
    *,
    corpus_path: Path | None = None,
    dimension: int = 128,
) -> dict:
    """Index a corpus (lexical + semantic) and return the retrievers."""
    corpus = corpus_path or copy_semantic_corpus(tmp_path)
    config = config_for(corpus)

    index = SqliteCorpusIndex(tmp_path / "corpus.db")
    manager = IndexManager(config, index)
    manager.initialize()
    manager.index_all()

    provider = HashingEmbeddingProvider(dimension=dimension)
    vector_index = SqliteVectorIndex(tmp_path / "vectors.db")
    vector_index.initialize()
    embed_manager = EmbeddingManager(index, vector_index, provider)
    embed_report = embed_manager.sync()

    lexical = LexicalRetriever(index)
    semantic = SemanticRetriever(index, vector_index, provider)
    hybrid = HybridRetriever(lexical, semantic)

    return {
        "corpus": corpus,
        "config": config,
        "index": index,
        "manager": manager,
        "provider": provider,
        "vector_index": vector_index,
        "embed_manager": embed_manager,
        "embed_report": embed_report,
        "lexical": lexical,
        "semantic": semantic,
        "hybrid": hybrid,
    }


def build_memory(tmp_path: Path) -> tuple[SqliteMemoryStore, MemoryService]:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    return store, MemoryService(store)
