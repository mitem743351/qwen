"""Filesystem discovery.

Walks configured corpus roots, enforces root containment and include/exclude
rules, detects supported files, computes metadata and content hash, and reports
candidate file records. Discovery is kept separate from ingestion: the scanner
never parses document content.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import os
from datetime import datetime
from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.corpus.hashing import hash_file
from qwen_research.corpus.records import FileRecord, FileStatus
from qwen_research.corpus.security import resolve_root

#: Extension → media type (best-effort, used for parser dispatch).
_MEDIA_TYPES: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".py": "text/x-python",
    ".rs": "text/x-rust",
    ".ts": "text/x-typescript",
    ".js": "text/javascript",
    ".sql": "text/x-sql",
    ".pdf": "application/pdf",
}


def media_type_for(extension: str) -> str:
    return _MEDIA_TYPES.get(extension.lower(), "application/octet-stream")


@dataclasses.dataclass(frozen=True)
class ScanResult:
    """Outcome of a scan: candidate records plus counts and known paths."""

    records: tuple[FileRecord, ...]
    scanned: int
    new: int
    changed: int
    unchanged: int
    missing: int
    unsupported: int
    too_large: int
    errors: int
    #: All discovered (path, hash) pairs for the current scan.
    discovered: dict[str, str]


class Scanner:
    """Discovers files under configured roots without parsing content."""

    def __init__(self, config: CorpusConfig) -> None:
        self._config = config

    def scan(
        self,
        *,
        known_hashes: dict[str, str] | None = None,
        root_ids: tuple[str, ...] | None = None,
    ) -> ScanResult:
        """Scan configured roots, classifying each discovered file.

        *known_hashes* maps a *relative path* to its previously indexed content
        hash (used to classify NEW/UNCHANGED/MODIFIED). *root_ids* restricts the
        scan to a subset of roots.
        """
        known = known_hashes or {}
        records: list[FileRecord] = []
        discovered: dict[str, str] = {}
        counts = {
            "scanned": 0,
            "new": 0,
            "changed": 0,
            "unchanged": 0,
            "missing": 0,
            "unsupported": 0,
            "too_large": 0,
            "errors": 0,
        }

        roots = [
            r
            for r in self._config.roots
            if r.enabled and (root_ids is None or r.root_id in root_ids)
        ]
        seen_paths: set[str] = set()

        for root in roots:
            root_path = resolve_root(root)
            if not root_path.is_dir():
                counts["errors"] += 1
                continue
            for dirpath, dirnames, filenames in os.walk(
                root_path, followlinks=self._config.follow_symlinks
            ):
                # Prune excluded directories in place.
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not self._excluded(root, root_path, Path(dirpath) / d)
                ]
                if not root.recursive:
                    dirnames[:] = []
                for filename in filenames:
                    full = Path(dirpath) / filename
                    counts["scanned"] += 1
                    try:
                        rel = str(full.relative_to(root_path))
                    except ValueError:
                        counts["errors"] += 1
                        continue
                    if self._excluded(root, root_path, full):
                        continue
                    extension = full.suffix
                    if not self._config.supports_extension(extension):
                        counts["unsupported"] += 1
                        continue
                    try:
                        record = self._classify(root, full, rel, known, counts)
                    except OSError:
                        counts["errors"] += 1
                        continue
                    records.append(record)
                    discovered[rel] = record.content_hash
                    seen_paths.add(rel)

        # Files previously indexed but no longer present are "missing".
        for rel in sorted(set(known) - seen_paths):
            counts["missing"] += 1
            records.append(
                FileRecord(
                    path="",
                    root_id="",
                    relative_path=rel,
                    extension=Path(rel).suffix,
                    media_type=media_type_for(Path(rel).suffix),
                    size_bytes=0,
                    modified_at=None,
                    content_hash="",
                    status=FileStatus.MISSING,
                )
            )

        return ScanResult(
            records=tuple(records),
            scanned=counts["scanned"],
            new=counts["new"],
            changed=counts["changed"],
            unchanged=counts["unchanged"],
            missing=counts["missing"],
            unsupported=counts["unsupported"],
            too_large=counts["too_large"],
            errors=counts["errors"],
            discovered=discovered,
        )

    def _excluded(self, root: CorpusRoot, root_path: Path, path: Path) -> bool:
        rel = str(path.relative_to(root_path))
        if self._config.is_excluded(rel):
            return True
        if root.exclude_patterns and any(
            _match(rel, p) for p in root.exclude_patterns
        ):
            return True
        if root.include_patterns:
            return not any(_match(rel, p) for p in root.include_patterns)
        return False

    def _classify(
        self,
        root: CorpusRoot,
        full: Path,
        rel: str,
        known: dict[str, str],
        counts: dict[str, int],
    ) -> FileRecord:
        size = full.stat().st_size
        modified = datetime.fromtimestamp(full.stat().st_mtime)
        if size > self._config.maximum_file_size:
            counts["too_large"] += 1
            return FileRecord(
                path=str(full),
                root_id=root.root_id,
                relative_path=rel,
                extension=full.suffix,
                media_type=media_type_for(full.suffix),
                size_bytes=size,
                modified_at=modified,
                content_hash="",
                status=FileStatus.TOO_LARGE,
            )
        content_hash = hash_file(full)
        if rel not in known:
            status = FileStatus.NEW
            counts["new"] += 1
        elif known[rel] == content_hash:
            status = FileStatus.UNCHANGED
            counts["unchanged"] += 1
        else:
            status = FileStatus.MODIFIED
            counts["changed"] += 1
        return FileRecord(
            path=str(full),
            root_id=root.root_id,
            relative_path=rel,
            extension=full.suffix,
            media_type=media_type_for(full.suffix),
            size_bytes=size,
            modified_at=modified,
            content_hash=content_hash,
            status=status,
        )


def _match(relative: str, pattern: str) -> bool:
    return fnmatch.fnmatch(relative, pattern)
