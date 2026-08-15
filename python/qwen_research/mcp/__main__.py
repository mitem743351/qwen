"""CLI entry point: run the MCP server over stdio.

Usage: ``python -m qwen_research.mcp``

Optional environment configuration:

- ``QWEN_RESEARCH_CORPUS_DB`` + ``QWEN_RESEARCH_CORPUS_ROOT`` — index a local
  corpus (SQLite FTS5) and expose ``search_corpus``/``get_source``.
- ``QWEN_RESEARCH_VECTOR_DB`` — enable semantic retrieval (embeddings stored in
  a local vector index). Combined with the corpus DB, ``search_corpus`` becomes
  hybrid by default.
- ``QWEN_RESEARCH_MEMORY_DB`` — enable persistent structured memory and the
  ``get_*_memory`` / ``save_research_memory`` tools.
- ``QWEN_RESEARCH_VERIFICATION_DB`` — enable the evidence-integrity layer
  (claims, evidence links, assessments, verification reports, contradictions).
- ``QWEN_RESEARCH_COMPUTATION_DB`` — enable the deterministic computation layer
  (DuckDB analytics + sandboxed Python), exposing ``describe_dataset`` /
  ``run_query`` / ``run_analysis`` / ``get_computation_result`` / ``run_python``.
- ``QWEN_RESEARCH_WORKSPACE_ROOT`` — output root for computation artifacts
  (default ``workspaces/computation``).
- ``QWEN_RESEARCH_ORCHESTRATION_DB`` — enable the research-orchestration layer
  (plans, workflow runs, events), exposing ``plan_research`` / ``start_research``
  / ``get_research_status`` / ``pause_research`` / ``resume_research`` /
  ``cancel_research`` / ``get_research_summary``.

Local-only: no network socket is opened.
"""

from __future__ import annotations

import os

from qwen_research.mcp.server import run_stdio_server
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.research.runtime import InMemoryResearchRuntime


def build_runtime() -> ResearchRuntime:
    """Build the Research Runtime, optionally wired to corpus/vectors/memory."""
    from qwen_research.retrieval.interface import Retriever

    retriever: Retriever | None = None
    memory = None

    corpus_db = os.environ.get("QWEN_RESEARCH_CORPUS_DB")
    corpus_root = os.environ.get("QWEN_RESEARCH_CORPUS_ROOT")
    vector_db = os.environ.get("QWEN_RESEARCH_VECTOR_DB")
    memory_db = os.environ.get("QWEN_RESEARCH_MEMORY_DB")
    verification_db = os.environ.get("QWEN_RESEARCH_VERIFICATION_DB")
    computation_db = os.environ.get("QWEN_RESEARCH_COMPUTATION_DB")
    workspace_root = os.environ.get("QWEN_RESEARCH_WORKSPACE_ROOT", "workspaces/computation")
    orchestration_db = os.environ.get("QWEN_RESEARCH_ORCHESTRATION_DB")

    config = None
    index = None
    if corpus_db and corpus_root:
        from qwen_research.corpus.config import CorpusConfig, CorpusRoot
        from qwen_research.indexing.manager import IndexManager
        from qwen_research.indexing.sqlite import SqliteCorpusIndex
        from qwen_research.retrieval.lexical import LexicalRetriever

        config = CorpusConfig(
            roots=(CorpusRoot(root_id="corpus", path=corpus_root, read_only=True, recursive=True),)
        )
        index = SqliteCorpusIndex(corpus_db)
        IndexManager(config, index).index_all()
        lexical = LexicalRetriever(index)

        if vector_db:
            from qwen_research.embeddings.hashing import HashingEmbeddingProvider
            from qwen_research.embeddings.manager import EmbeddingManager
            from qwen_research.retrieval.hybrid import HybridRetriever
            from qwen_research.retrieval.semantic import SemanticRetriever
            from qwen_research.vector.sqlite import SqliteVectorIndex

            provider = HashingEmbeddingProvider()
            vector_index = SqliteVectorIndex(vector_db)
            vector_index.initialize()
            EmbeddingManager(index, vector_index, provider).sync()
            hybrid = HybridRetriever(
                lexical,
                SemanticRetriever(index, vector_index, provider),
            )
            retriever = hybrid
        else:
            retriever = lexical

    if memory_db:
        from qwen_research.memory.provenance import validator_from_corpus
        from qwen_research.memory.service import MemoryService
        from qwen_research.memory.sqlite import SqliteMemoryStore

        store = SqliteMemoryStore(memory_db)
        store.initialize()
        validator = validator_from_corpus(index) if index is not None else None
        memory = MemoryService(store, validator=validator)

    verification = None
    if verification_db:
        from qwen_research.verification.service import EvidenceIntegrityService
        from qwen_research.verification.sqlite import SqliteVerificationStore

        vstore = SqliteVerificationStore(verification_db)
        vstore.initialize()
        verification = EvidenceIntegrityService(vstore, corpus_index=index)

    computation = None
    if computation_db and config is not None:
        from qwen_research.computation.artifacts import ArtifactStore
        from qwen_research.computation.datasets import DatasetResolver
        from qwen_research.computation.service import ComputationService
        from qwen_research.computation.store import ComputationStore

        cstore = ComputationStore(computation_db)
        cstore.initialize()
        resolver = DatasetResolver(config, index=index, artifacts_root=workspace_root)
        artifacts = ArtifactStore(workspace_root)
        computation = ComputationService(cstore, resolver, artifacts=artifacts)

    # Rebuild the memory validator with computation ids so research memory can
    # reference persisted computations (project-scoped).
    if memory_db and computation is not None and index is not None:
        from qwen_research.memory.provenance import ProvenanceValidator, validator_from_corpus
        from qwen_research.memory.service import MemoryService
        from qwen_research.memory.sqlite import SqliteMemoryStore

        store = SqliteMemoryStore(memory_db)
        store.initialize()
        base = validator_from_corpus(index)
        computations = computation.computation_ids_by_project()
        validator = ProvenanceValidator(
            sources=base.sources,
            evidence=base.evidence,
            claims=base.claims,
            computations=computations,
        )
        memory = MemoryService(store, validator=validator)

    orchestration = None
    if orchestration_db:
        from qwen_research.orchestration.capabilities import capability_registry_from_runtime
        from qwen_research.orchestration.service import OrchestrationService
        from qwen_research.orchestration.store import OrchestrationStore

        ostore = OrchestrationStore(orchestration_db)
        ostore.initialize()
        runtime = InMemoryResearchRuntime(
            retriever=retriever, memory=memory, verification=verification,
            computation=computation,
        )
        capabilities = capability_registry_from_runtime(
            retriever=retriever is not None,
            memory=memory is not None,
            verification=verification is not None,
            computation=computation is not None,
        )
        orchestration = OrchestrationService(
            ostore, runtime=runtime, capabilities=capabilities
        )
        runtime._orchestration = orchestration  # noqa: SLF001 — wiring boundary
        return runtime

    return InMemoryResearchRuntime(
        retriever=retriever, memory=memory, verification=verification, computation=computation
    )


def main() -> None:
    config = None
    if os.environ.get("QWEN_RESEARCH_ENABLE_WRITE") == "1":
        from qwen_research.mcp.config import MCPServerConfig

        config = MCPServerConfig(
            permissions={
                "read": True,
                "analyze": True,
                "write": True,
                "execute": False,
                "destructive": False,
            }
        )
    run_stdio_server(build_runtime(), config)


if __name__ == "__main__":
    main()
