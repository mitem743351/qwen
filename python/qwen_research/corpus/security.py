"""Path safety: enforce corpus-root containment and reject escapes.

The resolution flow is: request → root validation → normalized path →
filesystem. Any path that would escape a configured root (``../``, absolute
paths outside roots, symlink escapes) is rejected with
:class:`PathSecurityError`, whose message never includes the offending
absolute path.
"""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.domain.errors import PathSecurityError


def _normalize(path: str | Path) -> Path:
    p = Path(path)
    return p.resolve(strict=False) if p.is_absolute() else p


def resolve_within_root(root: CorpusRoot, relative: str) -> Path:
    """Resolve *relative* against *root*, enforcing containment.

    Rejects absolute paths, ``..`` traversal, and symlink escapes (the resolved
    real path must stay inside the resolved root). Returns the resolved,
    contained path.
    """
    root_path = _normalize(root.path)
    candidate = Path(relative)
    if candidate.is_absolute():
        raise PathSecurityError("absolute path outside corpus root")
    joined = root_path / candidate
    resolved = joined.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError:
        raise PathSecurityError("path escapes corpus root") from None
    return resolved


def resolve_root(root: CorpusRoot) -> Path:
    """Return the resolved, real path of a root."""
    return _normalize(root.path)


def resolve_file(root: CorpusRoot, relative: str, *, follow_symlinks: bool) -> Path:
    """Resolve *relative* under *root* for a concrete file.

    When *follow_symlinks* is False, any symlink component below the root is
    rejected **before** resolution (``Path.resolve`` follows symlinks, so a
    post-resolve check could never observe them).
    """
    root_path = _normalize(root.path)
    candidate = Path(relative)
    if candidate.is_absolute():
        raise PathSecurityError("absolute path outside corpus root")
    joined = root_path / candidate
    if not follow_symlinks:
        _reject_symlink_below(root_path, joined)
    resolved = joined.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError:
        raise PathSecurityError("path escapes corpus root") from None
    return resolved


def _reject_symlink_below(root_path: Path, path: Path) -> None:
    """Raise :class:`PathSecurityError` if any component below *root_path* is a symlink."""
    try:
        parts = path.relative_to(root_path).parts
    except ValueError:
        return  # not lexically under the root; the containment check handles it
    current = root_path
    for part in parts:
        if part == "..":
            if current != root_path:
                current = current.parent
            continue
        if part == ".":
            continue
        current = current / part
        if current.is_symlink():
            raise PathSecurityError("symlink escape rejected")


def is_safe_relative(relative: str) -> bool:
    """Return True if *relative* is a clean, non-escaping relative path."""
    p = Path(relative)
    if p.is_absolute():
        return False
    return all(part != ".." for part in p.parts)


def validate_roots(config: CorpusConfig) -> None:
    """Validate that all configured roots are absolute and distinct."""
    seen: set[str] = set()
    for root in config.roots:
        if not Path(root.path).is_absolute():
            raise PathSecurityError(f"corpus root {root.root_id!r} must be absolute")
        resolved = _normalize(root.path)
        key = str(resolved)
        if key in seen:
            raise PathSecurityError(f"duplicate corpus root {root.root_id!r}")
        seen.add(key)
