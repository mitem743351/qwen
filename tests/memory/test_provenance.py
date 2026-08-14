"""Regression: research-memory provenance hardening.

Research-derived references must resolve (project-scoped for claims) before a
memory record is persisted, and a partially valid record must never commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phase4_helpers import build_hybrid_stack, build_memory
from qwen_research.domain.errors import ProvenanceError
from qwen_research.memory.models import MemoryOrigin
from qwen_research.memory.provenance import (
    ProvenanceValidator,
    ReferenceKind,
    validator_from_corpus,
)
from qwen_research.memory.service import MemoryService
from qwen_research.memory.sqlite import SqliteMemoryStore


def _service_with_validator(
    tmp_path: Path, validator: ProvenanceValidator
) -> tuple[MemoryService, SqliteMemoryStore]:
    store, _ = build_memory(tmp_path)
    return MemoryService(store, validator=validator), store


def _validator(
    *,
    sources: frozenset[str] = frozenset(),
    evidence: frozenset[str] = frozenset(),
    claims: dict[str, frozenset[str]] | None = None,
) -> ProvenanceValidator:
    return ProvenanceValidator(sources=sources, evidence=evidence, claims=claims or {})


def test_valid_source_reference(tmp_path: Path) -> None:
    service, store = _service_with_validator(tmp_path, _validator(sources=frozenset({"s1"})))
    memory = service.save_research_memory("p", "claim", source_refs=("s1",))
    assert memory.source_refs == ("s1",)
    assert len(store.get_research_memory("p")) == 1


def test_missing_source_reference(tmp_path: Path) -> None:
    service, store = _service_with_validator(tmp_path, _validator(sources=frozenset()))
    with pytest.raises(ProvenanceError) as exc:
        service.save_research_memory("p", "claim", source_refs=("missing",))
    assert exc.value.kind == "source"
    assert exc.value.identifier == "missing"


def test_valid_evidence_reference(tmp_path: Path) -> None:
    service, store = _service_with_validator(tmp_path, _validator(evidence=frozenset({"e1"})))
    service.save_research_memory("p", "claim", evidence_refs=("e1",))
    assert len(store.get_research_memory("p")) == 1


def test_missing_evidence_reference(tmp_path: Path) -> None:
    service, _ = _service_with_validator(tmp_path, _validator(evidence=frozenset()))
    with pytest.raises(ProvenanceError) as exc:
        service.save_research_memory("p", "claim", evidence_refs=("missing",))
    assert exc.value.kind == "evidence"


def test_valid_claim_reference(tmp_path: Path) -> None:
    service, store = _service_with_validator(
        tmp_path, _validator(claims={"p": frozenset({"c1"})})
    )
    service.save_research_memory("p", "claim", claim_refs=("c1",))
    assert len(store.get_research_memory("p")) == 1


def test_missing_claim_reference(tmp_path: Path) -> None:
    service, _ = _service_with_validator(
        tmp_path, _validator(claims={"p": frozenset()})
    )
    with pytest.raises(ProvenanceError) as exc:
        service.save_research_memory("p", "claim", claim_refs=("missing",))
    assert exc.value.kind == "claim"


def test_mixed_valid_and_invalid_fails(tmp_path: Path) -> None:
    service, _ = _service_with_validator(
        tmp_path, _validator(sources=frozenset({"s1"}), evidence=frozenset())
    )
    with pytest.raises(ProvenanceError):
        service.save_research_memory("p", "claim", source_refs=("s1",), evidence_refs=("bad",))


def test_atomic_no_partial_write(tmp_path: Path) -> None:
    service, store = _service_with_validator(
        tmp_path, _validator(sources=frozenset({"s1"}))
    )
    with pytest.raises(ProvenanceError):
        service.save_research_memory("p", "claim", source_refs=("s1", "missing"))
    # Nothing was persisted.
    assert store.get_research_memory("p") == []


def test_cross_project_claim_reference_rejected(tmp_path: Path) -> None:
    # Claim "c1" is known only for project A; a save to project B must fail.
    service, store = _service_with_validator(
        tmp_path, _validator(claims={"A": frozenset({"c1"})})
    )
    with pytest.raises(ProvenanceError):
        service.save_research_memory("B", "claim", claim_refs=("c1",))
    assert store.get_research_memory("B") == []


def test_user_origin_metadata_not_validated(tmp_path: Path) -> None:
    service, store = _service_with_validator(tmp_path, _validator(sources=frozenset()))
    # User-originated metadata may reference arbitrary strings without failing.
    memory = service.save_research_memory(
        "p", "user note", source_refs=("arbitrary",), origin=MemoryOrigin.USER
    )
    assert memory.origin is MemoryOrigin.USER
    assert len(store.get_research_memory("p")) == 1


def test_no_validator_preserves_phase4_behavior(tmp_path: Path) -> None:
    store, _ = build_memory(tmp_path)
    service = MemoryService(store)  # no validator → no enforcement
    memory = service.save_research_memory("p", "claim", evidence_refs=("ev_1",))
    assert memory.evidence_refs == ("ev_1",)


def test_validator_from_corpus_resolves_sources_and_evidence(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    validator = validator_from_corpus(stack["index"])
    assert len(validator.sources) >= 1
    assert len(validator.evidence) >= 1
    # A real chunk id resolves as evidence; a fabricated one does not.
    real_chunk = next(iter(validator.evidence))
    assert validator.resolve("p", ReferenceKind.EVIDENCE, real_chunk) is True
    assert validator.resolve("p", ReferenceKind.EVIDENCE, "bogus") is False
