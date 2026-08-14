"""Evidence packaging.

Transforms a :class:`RetrievedChunk` into the Phase 1 :class:`Evidence` domain
object, carrying full provenance (source, location, excerpt, relevance).
``relevance`` is the search score, never model-derived confidence.
"""

from __future__ import annotations

from qwen_research.common.ids import SourceId
from qwen_research.domain.evidence import Evidence
from qwen_research.retrieval.models import RetrievedChunk


def to_evidence(chunk: RetrievedChunk) -> Evidence:
    """Package a retrieved chunk as structured, citable evidence."""
    location = chunk.relative_path or chunk.path or chunk.document_id
    if chunk.page is not None:
        location = f"{location}:p{chunk.page}"
    elif chunk.section:
        location = f"{location}#{chunk.section}"

    metadata = {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
    }
    if chunk.page is not None:
        metadata["page"] = str(chunk.page)
    if chunk.section:
        metadata["section"] = chunk.section
    if chunk.media_type:
        metadata["media_type"] = chunk.media_type

    return Evidence.create(
        source_id=SourceId(chunk.source_id),
        location=location,
        excerpt=chunk.text,
        relevance=chunk.score,
        metadata=metadata,
    )
