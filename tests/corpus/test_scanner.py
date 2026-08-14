"""Scanner tests: classification of new/unchanged/modified/missing/unsupported."""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.corpus.records import FileStatus
from qwen_research.corpus.scanner import Scanner


def _config(tmp_path: Path) -> CorpusConfig:
    return CorpusConfig(roots=(CorpusRoot(root_id="r", path=str(tmp_path)),))


def test_new_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("content")
    scan = Scanner(_config(tmp_path)).scan(known_hashes={})
    assert scan.new == 1
    record = scan.records[0]
    assert record.status is FileStatus.NEW
    assert record.extension == ".txt"
    assert record.content_hash


def test_unchanged_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("content")
    scanner = Scanner(_config(tmp_path))
    first = scanner.scan(known_hashes={})
    rel = first.records[0].relative_path
    known = {("r", rel): first.records[0].content_hash}
    second = scanner.scan(known_hashes=known)
    assert second.unchanged == 1
    assert second.records[0].status is FileStatus.UNCHANGED


def test_modified_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("content one")
    scanner = Scanner(_config(tmp_path))
    first = scanner.scan(known_hashes={})
    rel = first.records[0].relative_path
    f.write_text("content two, longer")
    second = scanner.scan(known_hashes={("r", rel): "0" * 64})
    assert second.changed == 1
    assert second.records[0].status is FileStatus.MODIFIED


def test_missing_file(tmp_path: Path) -> None:
    scanner = Scanner(_config(tmp_path))
    scan = scanner.scan(known_hashes={("r", "gone.txt"): "0" * 64})
    assert scan.missing == 1
    assert scan.records[0].status is FileStatus.MISSING
    assert scan.records[0].root_id == "r"


def test_unsupported_file(tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"\x00\x01")
    scan = Scanner(_config(tmp_path)).scan(known_hashes={})
    assert scan.unsupported == 1


def test_excluded_directory_skipped(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    scan = Scanner(_config(tmp_path)).scan(known_hashes={})
    assert scan.scanned >= 0
    assert all(r.relative_path != ".git/config" for r in scan.records)


def test_too_large_file(tmp_path: Path) -> None:
    f = tmp_path / "big.txt"
    f.write_bytes(b"a" * 2000)
    config = CorpusConfig(
        roots=(CorpusRoot(root_id="r", path=str(tmp_path)),),
        maximum_file_size=1000,
    )
    scan = Scanner(config).scan(known_hashes={})
    assert scan.too_large == 1
    assert scan.records[0].status is FileStatus.TOO_LARGE
