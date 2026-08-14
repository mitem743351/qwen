"""Typed corpus configuration.

Extends the Phase 1 configuration model with a corpus section. Safe defaults:
``follow_symlinks = False`` and ``read_only = True``.
"""

from __future__ import annotations

import dataclasses
import fnmatch
from pathlib import Path

from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class CorpusRoot:
    """A configured, allowlisted corpus directory."""

    root_id: str
    path: str
    name: str | None = None
    enabled: bool = True
    read_only: bool = True
    recursive: bool = True
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        return self.name or self.root_id


@serializable
@dataclasses.dataclass(frozen=True)
class CorpusConfig:
    """Configuration for the corpus subsystem."""

    roots: tuple[CorpusRoot, ...] = ()
    supported_extensions: tuple[str, ...] = (
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".py",
        ".rs",
        ".ts",
        ".js",
        ".sql",
        ".pdf",
    )
    excluded_patterns: tuple[str, ...] = (".git", "__pycache__", ".venv", "node_modules")
    maximum_file_size: int = 50 * 1024 * 1024  # 50 MiB
    follow_symlinks: bool = False
    indexing_workers: int = 2
    chunk_size: int = 1000
    chunk_overlap: int = 100

    def root_by_id(self, root_id: str) -> CorpusRoot:
        for root in self.roots:
            if root.root_id == root_id:
                return root
        raise KeyError(root_id)

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in {e.lower() for e in self.supported_extensions}

    def is_excluded(self, relative_path: str) -> bool:
        """Return whether a relative path matches an exclusion pattern."""
        parts = Path(relative_path).parts
        for pattern in self.excluded_patterns:
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        return False
