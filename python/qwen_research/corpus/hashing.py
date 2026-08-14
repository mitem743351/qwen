"""Stable content hashing for incremental indexing.

Uses SHA-256 over the raw bytes so content changes are detected independently
of filename changes. The hash is streamed in fixed blocks to bound memory for
large files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_BLOCK_SIZE = 1 << 20  # 1 MiB


def hash_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of the file at *path* (streamed)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_BLOCK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
