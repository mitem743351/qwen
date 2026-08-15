"""Content hashing for computation provenance.

Code and queries are hashed so a result can be traced to the exact source that
produced it — never by filename. SQL is normalized (whitespace collapsed,
case preserved) before hashing.
"""

from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def code_hash(source: str) -> str:
    """Return the SHA-256 hex digest of Python source code."""
    return hashlib.sha256(source.encode()).hexdigest()


def query_hash(query: str) -> str:
    """Return the SHA-256 hex digest of a normalized SQL query."""
    return hashlib.sha256(_normalize_query(query).encode()).hexdigest()


def _normalize_query(query: str) -> str:
    return _WS_RE.sub(" ", query.strip())
