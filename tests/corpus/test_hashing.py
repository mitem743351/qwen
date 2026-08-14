"""Content-hashing tests."""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.hashing import hash_bytes, hash_file


def test_same_content_same_hash(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    h1 = hash_file(f)
    h2 = hash_file(f)
    assert h1 == h2
    assert h1 == hash_bytes(b"hello world")


def test_modified_content_different_hash(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    h1 = hash_file(f)
    f.write_text("hello world, changed")
    h2 = hash_file(f)
    assert h1 != h2


def test_hash_independent_of_filename(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same content")
    b.write_text("same content")
    assert hash_file(a) == hash_file(b)


def test_hash_is_hex_sha256() -> None:
    assert len(hash_bytes(b"x")) == 64
