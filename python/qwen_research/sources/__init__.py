"""Source layer: source quality and independence."""

from qwen_research.sources.independence import (
    SourceIdentity,
    SourceIndependence,
    assess_independence,
    count_independent_sources,
)
from qwen_research.sources.quality import SourceQuality, SourceQualityAssessor, SourceTier

__all__ = [
    "SourceIdentity",
    "SourceIndependence",
    "SourceQuality",
    "SourceQualityAssessor",
    "SourceTier",
    "assess_independence",
    "count_independent_sources",
]
