"""Dataset resolution and profiling.

Datasets are referenced only through controlled identifiers
(:class:`~qwen_research.computation.models.DatasetReference`); every concrete
filesystem path is resolved through the corpus security layer. Arbitrary OS
paths from MCP are never accepted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from qwen_research.computation.models import DatasetReference
from qwen_research.corpus.config import CorpusConfig
from qwen_research.corpus.hashing import hash_file
from qwen_research.corpus.security import resolve_file, resolve_root
from qwen_research.domain.errors import DatasetError
from qwen_research.indexing.interface import CorpusIndex

_SUPPORTED_FORMATS = ("csv", "json", "parquet", "sqlite")


@dataclass(frozen=True)
class ResolvedDataset:
    """A dataset reference resolved to a concrete, contained path."""

    path: str
    format: str
    content_hash: str
    size_bytes: int
    dataset_id: str


def _format_for(path: str, requested: str | None) -> str:
    if requested:
        fmt = requested.lower()
        if fmt in _SUPPORTED_FORMATS:
            return fmt
        raise DatasetError(f"unsupported dataset format {requested!r}")
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix == "csv":
        return "csv"
    if suffix == "json":
        return "json"
    if suffix in ("parquet", "pq"):
        return "parquet"
    if suffix in ("sqlite", "db", "sqlite3"):
        return "sqlite"
    raise DatasetError(
        f"unsupported dataset file type {suffix!r} (expected csv/json/parquet/sqlite)"
    )


class DatasetResolver:
    """Resolve :class:`DatasetReference` values to contained filesystem paths.

    Resolution order: ``artifact_id`` (via the workspace/artifacts root),
    ``dataset_id``/``document_id`` (via the corpus index, which yields a
    ``root_id`` + ``relative_path``), then ``root_id`` + ``relative_path``
    directly. All paths pass through :func:`resolve_file`, which enforces root
    containment and rejects symlink escapes.
    """

    def __init__(
        self,
        config: CorpusConfig,
        *,
        index: CorpusIndex | None = None,
        artifacts_root: str | None = None,
    ) -> None:
        self._config = config
        self._index = index
        self._artifacts_root = artifacts_root

    def resolve(self, reference: DatasetReference) -> ResolvedDataset:
        root_id, relative = self._locate(reference)
        if root_id is None or relative is None:
            raise DatasetError("dataset reference cannot be resolved to a corpus path")
        try:
            root = self._config.root_by_id(root_id)
        except KeyError:
            raise DatasetError(f"unknown corpus root {root_id!r}") from None

        path = resolve_file(root, relative, follow_symlinks=self._config.follow_symlinks)
        if not path.is_file():
            raise DatasetError(f"dataset file not found: {relative}")
        size = path.stat().st_size
        fmt = _format_for(str(path), reference.format)
        content_hash = hash_file(path)
        dataset_id = _dataset_id(str(path), content_hash)
        return ResolvedDataset(
            path=str(path),
            format=fmt,
            content_hash=content_hash,
            size_bytes=size,
            dataset_id=dataset_id,
        )

    def _locate(self, reference: DatasetReference) -> tuple[str | None, str | None]:
        if reference.artifact_id is not None:
            if self._artifacts_root is None:
                raise DatasetError("artifact datasets require an artifacts root")
            return None, None  # handled separately; artifact inputs unsupported here
        if reference.document_id is not None or reference.dataset_id is not None:
            doc_id = reference.document_id or reference.dataset_id
            assert doc_id is not None
            if self._index is None:
                raise DatasetError("document/dataset id resolution requires a corpus index")
            view = self._index.get_document(doc_id)
            if view is None:
                raise DatasetError(f"dataset document {doc_id!r} not found in corpus")
            return view.root_id, view.relative_path
        if reference.root_id is not None and reference.relative_path is not None:
            return reference.root_id, reference.relative_path
        raise DatasetError("dataset reference must specify root_id/relative_path or a document id")


def _dataset_id(path: str, content_hash: str) -> str:
    digest = hashlib.sha256(f"{path}\x00{content_hash}".encode()).hexdigest()
    return f"dataset_{digest[:16]}"


def dataset_id_for_path(path: str) -> str:
    """Return a stable dataset id from a path and its current content hash."""
    return _dataset_id(path, hash_file(path))


def resolve_root_path(config: CorpusConfig, root_id: str) -> Path:
    """Return the resolved real path of a configured root (for output roots)."""
    try:
        root = config.root_by_id(root_id)
    except KeyError:
        raise DatasetError(f"unknown corpus root {root_id!r}") from None
    return resolve_root(root)
