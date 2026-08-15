"""Artifact store tests (containment + traversal rejection)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.computation.artifacts import ArtifactStore
from qwen_research.domain.errors import PathSecurityError


def test_save_and_read_json(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "out")
    rel = store.save_json({"a": 1, "b": [2, 3]})
    assert store.read_text(rel).startswith("{")
    assert (tmp_path / "out" / rel).exists()


def test_save_csv(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "out")
    rel = store.save_csv(("a", "b"), [(1, 2), (3, 4)])
    assert store.read_text(rel) == "a,b\n1,2\n3,4\n"


@pytest.mark.parametrize(
    "name",
    ["../escape.txt", "/abs/path.txt", "a/b/../../escape.json"],
)
def test_path_traversal_rejected(tmp_path: Path, name: str) -> None:
    store = ArtifactStore(tmp_path / "out")
    with pytest.raises(PathSecurityError):
        store.save_text("x", name=name)
