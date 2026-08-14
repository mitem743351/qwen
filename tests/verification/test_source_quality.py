"""Source quality and independence unit tests."""

from __future__ import annotations

from qwen_research.sources.independence import SourceIndependence, assess_independence
from qwen_research.sources.quality import SourceQualityAssessor, SourceTier


def _assessor() -> SourceQualityAssessor:
    return SourceQualityAssessor()


def test_tier_1_primary_source() -> None:
    q = _assessor().assess(media_type="application/pdf", metadata={"primary_source": "true"})
    assert q.tier is SourceTier.TIER_1
    assert q.primary_source is True


def test_tier_2_peer_reviewed() -> None:
    q = _assessor().assess(media_type="application/pdf", metadata={"peer_reviewed": "true"})
    assert q.tier is SourceTier.TIER_2
    assert q.peer_reviewed is True


def test_tier_3_institutional() -> None:
    q = _assessor().assess(media_type="text/plain", metadata={"institutional": "true"})
    assert q.tier is SourceTier.TIER_3


def test_explicit_source_tier_overrides() -> None:
    q = _assessor().assess(media_type="text/plain", metadata={"source_tier": "tier_1"})
    assert q.tier is SourceTier.TIER_1


def test_default_is_tier_5() -> None:
    q = _assessor().assess(media_type="text/plain", metadata={})
    assert q.tier is SourceTier.TIER_5


def test_provenance_completeness() -> None:
    incomplete = _assessor().assess(media_type="text/plain", metadata={})
    assert incomplete.provenance_completeness == "incomplete"
    complete = _assessor().assess(media_type="text/plain", metadata={"content_hash": "h"})
    assert complete.provenance_completeness == "complete"


def test_extraction_quality_from_metadata() -> None:
    q = _assessor().assess(media_type="application/pdf", metadata={"parse_status": "unextractable"})
    assert q.extraction_quality == "unextractable"


def test_independence_same_document() -> None:
    r = assess_independence(
        document_a="d1", document_b="d1", source_a="s1", source_b="s2",
        publisher_a=None, publisher_b=None, root_a=None, root_b=None,
    )
    assert r is SourceIndependence.DEPENDENT


def test_independence_same_source() -> None:
    r = assess_independence(
        document_a="d1", document_b="d2", source_a="s1", source_b="s1",
        publisher_a=None, publisher_b=None, root_a=None, root_b=None,
    )
    assert r is SourceIndependence.DEPENDENT


def test_independence_same_publisher() -> None:
    r = assess_independence(
        document_a="d1", document_b="d2", source_a="s1", source_b="s2",
        publisher_a="acme", publisher_b="acme", root_a=None, root_b=None,
    )
    assert r is SourceIndependence.DEPENDENT


def test_independence_independent() -> None:
    r = assess_independence(
        document_a="d1", document_b="d2", source_a="s1", source_b="s2",
        publisher_a="acme", publisher_b="beta", root_a=None, root_b=None,
    )
    assert r is SourceIndependence.INDEPENDENT


def test_independence_unknown() -> None:
    r = assess_independence(
        document_a=None, document_b=None, source_a=None, source_b=None,
        publisher_a=None, publisher_b=None, root_a=None, root_b=None,
    )
    assert r is SourceIndependence.UNKNOWN
