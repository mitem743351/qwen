"""Regression: symlink enforcement.

When ``follow_symlinks`` is False (the default), symlinked files must not be
indexed (they could escape the corpus root), and ``resolve_file`` must reject
symlink components before resolution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.corpus.scanner import Scanner
from qwen_research.corpus.security import resolve_file
from qwen_research.domain.errors import PathSecurityError


def _config(root: Path, *, follow_symlinks: bool = False) -> CorpusConfig:
    return CorpusConfig(
        roots=(CorpusRoot(root_id="r", path=str(root), read_only=True, recursive=True),),
        follow_symlinks=follow_symlinks,
    )


def test_scanner_skips_symlinked_files(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret data that must not be indexed")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "leak.txt"
    link.symlink_to(outside)

    scan = Scanner(_config(root)).scan(known_hashes={})
    # The symlinked file is not indexed and not counted as new.
    assert scan.new == 0
    assert all(r.relative_path != "leak.txt" for r in scan.records)


def test_scanner_follows_symlinks_when_enabled(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("linked content")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "leak.txt"
    link.symlink_to(outside)

    scan = Scanner(_config(root, follow_symlinks=True)).scan(known_hashes={})
    assert scan.new == 1
    assert scan.records[0].relative_path == "leak.txt"


def test_resolve_file_rejects_symlink_component(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    link = root_dir / "leak.txt"
    link.symlink_to(outside)
    root = CorpusRoot(root_id="r", path=str(root_dir))

    with pytest.raises(PathSecurityError):
        resolve_file(root, "leak.txt", follow_symlinks=False)


def test_resolve_file_allows_clean_path(tmp_path: Path) -> None:
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "ok.txt").write_text("ok")
    root = CorpusRoot(root_id="r", path=str(root_dir))

    resolved = resolve_file(root, "ok.txt", follow_symlinks=False)
    assert resolved == (root_dir / "ok.txt").resolve()


def test_resolve_file_rejects_symlinked_directory_component(tmp_path: Path) -> None:
    outside_dir = tmp_path.parent / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "x.txt").write_text("secret")
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    (root_dir / "sub").symlink_to(outside_dir)
    root = CorpusRoot(root_id="r", path=str(root_dir))

    with pytest.raises(PathSecurityError):
        resolve_file(root, "sub/x.txt", follow_symlinks=False)
