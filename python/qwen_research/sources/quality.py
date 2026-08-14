"""Source-quality model and deterministic baseline assessor.

Source quality is a structured assessment of source *characteristics*, fully
independent of retrieval relevance and never a claim of truth. The baseline
assessor is deterministic and config-driven: it reads explicit document
metadata and applies rules — no LLM judge and no web scraping.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from enum import StrEnum

from qwen_research.common.serialization import serializable


class SourceTier(StrEnum):
    """A configurable source hierarchy.

    Tier represents source characteristics, **not** truth — a Tier-1 source is
    not assumed to be correct.
    """

    TIER_1 = "tier_1"  # primary source, official dataset, standard, original result
    TIER_2 = "tier_2"  # peer-reviewed secondary research, systematic review
    TIER_3 = "tier_3"  # reputable technical/institutional source
    TIER_4 = "tier_4"  # secondary web source, reporting, commentary
    TIER_5 = "tier_5"  # unverified / low-provenance material


@serializable
@dataclasses.dataclass(frozen=True)
class SourceQuality:
    """A structured source-quality assessment."""

    tier: SourceTier
    authority: str | None = None
    primary_source: bool = False
    peer_reviewed: bool = False
    recency: str | None = None
    provenance_completeness: str = "unknown"
    extraction_quality: str = "unknown"
    notes: str = ""


def _tier_from_metadata(metadata: Mapping[str, str]) -> SourceTier:
    """Map explicit metadata to a tier; defaults to TIER_5 (low provenance)."""
    explicit = metadata.get("source_tier")
    if explicit:
        try:
            return SourceTier(explicit.lower())
        except ValueError:
            pass
    if metadata.get("primary_source") in ("true", "1"):
        return SourceTier.TIER_1
    if metadata.get("peer_reviewed") in ("true", "1"):
        return SourceTier.TIER_2
    if metadata.get("institutional") in ("true", "1"):
        return SourceTier.TIER_3
    media_type = metadata.get("media_type", "")
    if media_type == "application/pdf":
        return SourceTier.TIER_2 if metadata.get("peer_reviewed") else SourceTier.TIER_3
    return SourceTier.TIER_5


class SourceQualityAssessor:
    """Deterministic baseline source-quality assessor."""

    def assess(
        self,
        *,
        media_type: str,
        metadata: Mapping[str, str],
    ) -> SourceQuality:
        tier = _tier_from_metadata({**dict(metadata), "media_type": media_type})
        primary = metadata.get("primary_source") in ("true", "1")
        peer_reviewed = metadata.get("peer_reviewed") in ("true", "1")
        authority = metadata.get("authority") or metadata.get("publisher")
        recency = metadata.get("publication_date")
        extraction = metadata.get("parse_status", "unknown")

        completeness = "complete" if metadata.get("content_hash") else "incomplete"
        return SourceQuality(
            tier=tier,
            authority=authority,
            primary_source=primary,
            peer_reviewed=peer_reviewed,
            recency=recency,
            provenance_completeness=completeness,
            extraction_quality=extraction,
            notes=metadata.get("quality_notes", ""),
        )
