"""Full-stack restart test: index → close → reopen → search + memory."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import copy_semantic_corpus
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


def test_full_stack_restart(tmp_path: Path) -> None:
    corpus = copy_semantic_corpus(tmp_path)
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="semantic", path=str(corpus), read_only=True, recursive=True),)
    )

    # --- first process: index corpus + embed + save memory ---
    index = SqliteCorpusIndex(tmp_path / "corpus.db")
    IndexManager(config, index).index_all()

    provider = HashingEmbeddingProvider()
    vector_index = SqliteVectorIndex(tmp_path / "vectors.db")
    vector_index.initialize()
    EmbeddingManager(index, vector_index, provider).sync()

    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.initialize()
    MemoryService(store).save_research_memory("p", "persisted memory", evidence_refs=("e1",))

    index.close()
    vector_index.close()
    store.close()

    # --- second process: reopen everything and query ---
    index2 = SqliteCorpusIndex(tmp_path / "corpus.db")
    index2.initialize()
    provider2 = HashingEmbeddingProvider()
    vector2 = SqliteVectorIndex(tmp_path / "vectors.db")
    vector2.initialize()
    hybrid = HybridRetriever(
        LexicalRetriever(index2),
        SemanticRetriever(index2, vector2, provider2),
    )
    result = hybrid.search("methods for reducing quantum error rates")
    assert result.returned_count >= 1

    store2 = SqliteMemoryStore(tmp_path / "memory.db")
    store2.initialize()
    assert len(store2.get_research_memory("p")) == 1
