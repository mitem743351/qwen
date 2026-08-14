"""Shared retrieval filters.

Applies metadata filters to an already-retrieved candidate list. Used by the
semantic retriever (which has no native backend filtering) so that filters are
applied **before** final top-K truncation, and by the lexical retriever for the
filters the backend cannot express (date range, minimum score).

Order (documented): roots → document_types → path_prefix → date_range →
minimum_score. Ranking and diversity happen after filtering, then the final
limit truncates.
"""

from __future__ import annotations

from qwen_research.retrieval.models import RetrievedChunk, SearchOptions


def _matches_prefix(relative_path: str | None, prefix: str) -> bool:
    if not relative_path:
        return False
    prefix = prefix.rstrip("/")
    if not prefix:
        return True
    return relative_path == prefix or relative_path.startswith(prefix + "/")


def apply_filters(
    chunks: list[RetrievedChunk], options: SearchOptions
) -> list[RetrievedChunk]:
    """Return *chunks* filtered by *options* (no truncation)."""
    out: list[RetrievedChunk] = []
    for chunk in chunks:
        if options.roots and chunk.root_id not in options.roots:
            continue
        if options.document_types and chunk.media_type not in options.document_types:
            continue
        if options.path_prefix and not _matches_prefix(chunk.relative_path, options.path_prefix):
            continue
        if options.date_range:
            lo, hi = options.date_range
            if chunk.modified_at is None:
                continue
            if lo is not None and chunk.modified_at < lo:
                continue
            if hi is not None and chunk.modified_at > hi:
                continue
        if options.minimum_score is not None and chunk.score < options.minimum_score:
            continue
        out.append(chunk)
    return out
