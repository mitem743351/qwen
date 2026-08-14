"""Corpus path-security tests: containment, traversal, symlink escapes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.corpus.security import (
    is_safe_relative,
    resolve_within_root,
    validate_roots,
)
from qwen_research.domain.errors import PathSecurityError


def _root(path: str) -> CorpusRoot:
    return CorpusRoot(root_id="r", path=path)


def test_resolve_within_root_accepts_clean_relative(tmp_path: Path) -> None:
    root = _root(str(tmp_path))
    target = tmp_path / "notes" / "a.txt"
    target.parent.mkdir()
    target.write_text("hi")
    resolved = resolve_within_root(root, "notes/a.txt")
    assert resolved == target.resolve()


def test_resolve_within_root_rejects_absolute(tmp_path: Path) -> None:
    root = _root(str(tmp_path))
    with pytest.raises(PathSecurityError):
        resolve_within_root(root, "/etc/passwd")


def test_resolve_within_root_rejects_parent_traversal(tmp_path: Path) -> None:
    root = _root(str(tmp_path))
    with pytest.raises(PathSecurityError):
        resolve_within_root(root, "../outside.txt")


def test_resolve_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret")
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    link = root_dir / "link.txt"
    link.symlink_to(outside)
    root = _root(str(root_dir))
    with pytest.raises(PathSecurityError):
        resolve_within_root(root, "link.txt")


def test_is_safe_relative() -> None:
    assert is_safe_relative("notes/a.txt")
    assert not is_safe_relative("../a.txt")
    assert not is_safe_relative("/abs/a.txt")
    assert not is_safe_relative("a/../../b.txt")


def test_validate_roots_rejects_relative(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path="relative/path"),))
    with pytest.raises(PathSecurityError):
        validate_roots(config)


def test_validate_roots_accepts_absolute(tmp_path: Path) -> None:
    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(tmp_path)),))
    validate_roots(config)


def test_excluded_patterns(tmp_path: Path) -> None:
    from qwen_research.corpus.config import CorpusConfig

    config = CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(tmp_path)),))
    assert config.is_excluded(".git/config")
    assert config.is_excluded("a/b/__pycache__/x.py")
    assert not config.is_excluded("notes/a.txt")
