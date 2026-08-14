"""The Evidence domain object."""

from __future__ import annotations

import dataclasses

from qwen_research.common.ids import EvidenceId, SourceId, new_id
from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class Evidence:
    """Evidence extracted from a source.

    This is the contract only: ``location`` and ``excerpt`` are references,
    not the result of extraction (which belongs to later phases).
    """

    evidence_id: EvidenceId
    source_id: SourceId
    location: str
    excerpt: str
    relevance: float | None = None
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        source_id: SourceId,
        location: str,
        excerpt: str,
        *,
        relevance: float | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Evidence:
        return cls(
            evidence_id=EvidenceId(new_id("evidence")),
            source_id=source_id,
            location=location,
            excerpt=excerpt,
            relevance=relevance,
            metadata=dict(metadata or {}),
        )
