"""Helpers for Phase 7 orchestration tests.

Build a fully-wired Research Runtime (retrieval + memory + verification +
computation + orchestration) over a single shared corpus so evidence ids are
consistent across subsystems.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from phase4_helpers import build_hybrid_stack
from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.computation.datasets import DatasetResolver
from qwen_research.computation.service import ComputationService
from qwen_research.computation.store import ComputationStore
from qwen_research.memory.service import MemoryService
from qwen_research.memory.sqlite import SqliteMemoryStore
from qwen_research.orchestration.capabilities import capability_registry_from_runtime
from qwen_research.orchestration.service import OrchestrationService
from qwen_research.orchestration.store import OrchestrationStore
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.verification.service import EvidenceIntegrityService
from qwen_research.verification.sqlite import SqliteVerificationStore

SEMANTIC_CORPUS = Path(__file__).resolve().parent / "fixtures" / "semantic"


def build_corpus(tmp_path: Path) -> Path:
    """Copy the semantic corpus and add a CSV dataset for computation."""
    dest = tmp_path / "corpus"
    shutil.copytree(SEMANTIC_CORPUS, dest)
    (dest / "numbers.csv").write_text("group,value\nA,1.0\nA,2.0\nB,3.0\nB,5.0\nB,7.0\n")
    return dest


def build_stack(
    tmp_path: Path,
    *,
    enable_python_execution: bool = False,
) -> dict:
    """Build a fully-wired runtime and return all services/stores."""
    corpus = build_corpus(tmp_path)
    stack = build_hybrid_stack(tmp_path, corpus_path=corpus)

    memory_store = SqliteMemoryStore(tmp_path / "memory.db")
    memory_store.initialize()
    memory = MemoryService(memory_store)

    vstore = SqliteVerificationStore(tmp_path / "verification.db")
    vstore.initialize()
    verification = EvidenceIntegrityService(vstore, corpus_index=stack["index"])

    cstore = ComputationStore(tmp_path / "computation.db")
    cstore.initialize()
    resolver = DatasetResolver(
        stack["config"], index=stack["index"], artifacts_root=str(tmp_path / "artifacts")
    )
    computation = ComputationService(
        cstore,
        resolver,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        enable_python_execution=enable_python_execution,
    )

    ostore = OrchestrationStore(tmp_path / "orchestration.db")
    ostore.initialize()

    runtime = InMemoryResearchRuntime(
        retriever=stack["hybrid"],
        memory=memory,
        verification=verification,
        computation=computation,
    )
    capabilities = capability_registry_from_runtime(
        retriever=True, memory=True, verification=True, computation=True
    )
    orchestration = OrchestrationService(ostore, runtime=runtime, capabilities=capabilities)
    runtime._orchestration = orchestration  # noqa: SLF001 — test wiring
    return {
        "runtime": runtime,
        "orchestration_store": ostore,
        "memory_store": memory_store,
        "verification_store": vstore,
        "computation_store": cstore,
        "stack": stack,
    }


def build_runtime(
    tmp_path: Path,
    *,
    enable_python_execution: bool = False,
) -> tuple[InMemoryResearchRuntime, OrchestrationStore, dict]:
    """Convenience wrapper returning (runtime, orchestration store, hybrid stack)."""
    s = build_stack(tmp_path, enable_python_execution=enable_python_execution)
    return s["runtime"], s["orchestration_store"], s["stack"]
