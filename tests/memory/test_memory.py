"""Memory tests: creation, versioning, questions, provenance, isolation, retrieval."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_memory
from qwen_research.memory.models import MemoryOrigin, MemoryType, QuestionStatus
from qwen_research.memory.retriever import MemoryRetriever


def test_project_memory_creation_and_retrieval(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service._store.save_project_memory(
        __import__("qwen_research.memory.models", fromlist=["ProjectMemory"]).ProjectMemory.create(
            "projA", "The project concerns fault-tolerant quantum computing."
        )
    )
    items = store.get_project_memory("projA")
    assert len(items) == 1
    assert "fault-tolerant" in items[0].content


def test_research_memory_provenance(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    memory = service.save_research_memory(
        "projA",
        "Surface codes achieve ~1% threshold.",
        source_refs=("src_1",),
        evidence_refs=("ev_1",),
        provenance={"document_id": "doc_1"},
    )
    assert memory.source_refs == ("src_1",)
    assert memory.evidence_refs == ("ev_1",)
    assert memory.origin is MemoryOrigin.RESEARCH
    assert memory.provenance["document_id"] == "doc_1"

    retrieved = store.get_research_memory("projA")
    assert len(retrieved) == 1
    assert retrieved[0].source_refs == ("src_1",)


def test_user_vs_research_origin(tmp_path: Path) -> None:
    from qwen_research.memory.models import ProjectMemory

    store, service = build_memory(tmp_path)
    store.save_project_memory(
        ProjectMemory.create("p", "user-provided scope note", origin=MemoryOrigin.USER)
    )
    service.save_research_memory("p", "derived claim", evidence_refs=("e1",))
    pm = store.get_project_memory("p")
    rm = store.get_research_memory("p")
    assert pm[0].origin is MemoryOrigin.USER
    assert rm[0].origin is MemoryOrigin.RESEARCH


def test_question_lifecycle(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    q = service.save_open_question("p", "What is the surface code threshold?", priority=3)
    assert q.status is QuestionStatus.OPEN
    updated = service.update_question_status("p", q.question_id, QuestionStatus.ANSWERED)
    assert updated is not None
    assert updated.status is QuestionStatus.ANSWERED
    assert updated.version == q.version + 1
    # History is preserved (the answered question is still retrievable).
    assert any(x.question_id == q.question_id for x in store.get_questions("p"))


def test_decision_provenance(tmp_path: Path) -> None:
    from qwen_research.memory.models import DecisionRecord

    store, service = build_memory(tmp_path)
    store.save_decision(
        DecisionRecord.create(
            "p", "Use surface code as baseline", "well-documented threshold",
            evidence_refs=("ev_1",), source_refs=("src_2",),
        )
    )
    decisions = store.get_decisions("p")
    assert len(decisions) == 1
    assert decisions[0].evidence_refs == ("ev_1",)
    assert decisions[0].source_refs == ("src_2",)


def test_source_memory(tmp_path: Path) -> None:
    from qwen_research.memory.models import SourceMemory

    store, service = build_memory(tmp_path)
    store.save_source_memory(
        SourceMemory.create("p", "src_1", importance="key reference", topics=("qec", "threshold"))
    )
    items = store.get_source_memory("p")
    assert items[0].topics == ("qec", "threshold")
    assert items[0].importance == "key reference"


def test_project_isolation(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service.save_research_memory("projA", "claim in A", evidence_refs=("e1",))
    service.save_research_memory("projB", "claim in B", evidence_refs=("e2",))
    assert len(store.get_research_memory("projA")) == 1
    assert len(store.get_research_memory("projB")) == 1
    assert store.get_research_memory("projA")[0].content == "claim in A"


def test_session_memory_isolation(tmp_path: Path) -> None:
    from qwen_research.memory.models import SessionMemoryItem

    store, service = build_memory(tmp_path)
    store.save_session_item(
        SessionMemoryItem.create("s1", "p", "hypothesis", {"text": "H1"})
    )
    store.save_session_item(
        SessionMemoryItem.create("s2", "p", "hypothesis", {"text": "H2"})
    )
    assert len(store.get_session_items("s1")) == 1
    assert len(store.get_session_items("s2")) == 1
    assert store.get_session_items("s1")[0].content["text"] == "H1"


def test_structured_memory_retrieval(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service.save_research_memory("p", "surface code threshold", evidence_refs=("e1",))
    service.save_research_memory("p", "unrelated pottery claim", evidence_refs=("e2",))
    retriever = MemoryRetriever(store)
    hits = retriever.search("p", "surface code", memory_type=MemoryType.RESEARCH)
    assert hits[0].content == "surface code threshold"
    assert hits[0].score == 1.0


def test_open_questions_filter(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    service.save_open_question("p", "question one")
    q2 = service.save_open_question("p", "question two")
    service.update_question_status("p", q2.question_id, QuestionStatus.ANSWERED)
    retriever = MemoryRetriever(store)
    open_questions = retriever.open_questions("p", status=QuestionStatus.OPEN)
    assert len(open_questions) == 1
