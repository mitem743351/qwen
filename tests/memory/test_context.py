"""Context assembly and memory persistence tests."""

from __future__ import annotations

import threading
from pathlib import Path

from phase4_helpers import build_hybrid_stack, build_memory
from qwen_research.memory.context import ContextBudget, build_context
from qwen_research.research.runtime import InMemoryResearchRuntime


def test_build_context_combines_evidence_and_memory(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    store, service = build_memory(tmp_path)
    service.save_research_memory("default", "surface code threshold ~1%", evidence_refs=("e1",))
    service.save_open_question("default", "Is the threshold model-dependent?")

    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"], memory=service)
    context = runtime.build_research_context("quantum error rates")

    assert context.query == "quantum error rates"
    assert len(context.evidence) >= 1
    assert len(context.memories) >= 1
    assert len(context.open_questions) >= 1


def test_context_respects_budget(tmp_path: Path) -> None:
    evidence = [object() for _ in range(20)]
    budget = ContextBudget(max_evidence_chunks=5, max_memory_items=2, max_open_questions=1)
    ctx = build_context("q", evidence=evidence, budget=budget)  # type: ignore[arg-type]
    assert len(ctx.evidence) == 5


def test_memory_store_persistence_across_restart(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service.save_research_memory("p", "persistent claim", evidence_refs=("e1",))
    store.close()

    store2, service2 = build_memory(tmp_path)
    assert len(store2.get_research_memory("p")) == 1


def test_memory_store_schema_version(tmp_path: Path) -> None:
    import sqlite3

    store, service = build_memory(tmp_path)
    conn = sqlite3.connect(tmp_path / "memory.db")
    version = conn.execute("SELECT value FROM memory_meta WHERE key='schema_version'").fetchone()[0]
    conn.close()
    assert version == "1"


def test_concurrent_reads_and_controlled_writes(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service.save_research_memory("p", "seed", evidence_refs=("e0",))

    results: list[int] = []

    def reader() -> None:
        for _ in range(20):
            results.append(len(store.get_research_memory("p")))

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    service.save_research_memory("p", "concurrent write", evidence_refs=("e9",))
    for t in threads:
        t.join()
    # Every read observed either the seed or the seed + write (never partial).
    assert all(r in (1, 2) for r in results)


def test_search_corpus_without_retriever_in_context(tmp_path: Path) -> None:
    _, service = build_memory(tmp_path)
    runtime = InMemoryResearchRuntime(memory=service)
    ctx = runtime.build_research_context("anything")
    assert ctx.evidence == ()
