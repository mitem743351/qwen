"""Memory ↔ computation integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from computation_helpers import build_service, ref
from phase4_helpers import build_memory
from qwen_research.computation.models import ComputationOperation
from qwen_research.domain.errors import ProvenanceError
from qwen_research.memory.models import MemoryOrigin
from qwen_research.memory.provenance import ProvenanceValidator
from qwen_research.memory.service import MemoryService


def test_research_memory_records_computation_refs(tmp_path: Path) -> None:
    store, service = build_memory(tmp_path)
    memory = service.save_research_memory(
        "p", "conclusion", computation_refs=("comp_1",), dataset_refs=("dataset_x",)
    )
    assert memory.computation_refs == ("comp_1",)
    assert memory.dataset_refs == ("dataset_x",)
    loaded = store.get_research_memory("p")[0]
    assert loaded.computation_refs == ("comp_1",)
    assert loaded.dataset_refs == ("dataset_x",)


def test_unpersisted_computation_reference_rejected(tmp_path: Path) -> None:
    store, _ = build_memory(tmp_path)
    validator = ProvenanceValidator(computations={"p": frozenset({"comp_known"})})
    service = MemoryService(store, validator=validator)
    with pytest.raises(ProvenanceError):
        service.save_research_memory("p", "bad", computation_refs=("comp_unknown",))


def test_computation_reference_project_scoped(tmp_path: Path) -> None:
    store, _ = build_memory(tmp_path)
    validator = ProvenanceValidator(computations={"A": frozenset({"comp_1"})})
    service = MemoryService(store, validator=validator)
    # comp_1 belongs to project A, so it must not validate in project B.
    with pytest.raises(ProvenanceError):
        service.save_research_memory("B", "cross-project", computation_refs=("comp_1",))


def test_computation_ids_by_project(tmp_path: Path) -> None:
    service, _, _, _, data = build_service(tmp_path)
    service.run_analysis("A", (ref(data, "numbers.csv"),), ComputationOperation.COUNT)
    ids = service.computation_ids_by_project()
    assert "A" in ids
    assert len(ids["A"]) == 1


def test_user_origin_memory_exempt_from_computation_validation(tmp_path: Path) -> None:
    store, _ = build_memory(tmp_path)
    validator = ProvenanceValidator(computations={})
    service = MemoryService(store, validator=validator)
    memory = service.save_research_memory(
        "p", "note", computation_refs=("comp_any",), origin=MemoryOrigin.USER
    )
    assert memory.computation_refs == ("comp_any",)
