"""Source-independence heuristic.

Determines whether two evidence items come from independent sources. This is a
**basic heuristic** over available metadata (document, source, publisher, corpus
root) — it does not claim actual editorial independence.
"""

from __future__ import annotations

from enum import StrEnum


class SourceIndependence(StrEnum):
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"
    UNKNOWN = "unknown"


def assess_independence(
    *,
    document_a: str | None,
    document_b: str | None,
    source_a: str | None,
    source_b: str | None,
    publisher_a: str | None,
    publisher_b: str | None,
    root_a: str | None,
    root_b: str | None,
) -> SourceIndependence:
    """Return INDEPENDENT / DEPENDENT / UNKNOWN for two evidence items."""
    if document_a is not None and document_a == document_b:
        return SourceIndependence.DEPENDENT
    if source_a is not None and source_a == source_b:
        return SourceIndependence.DEPENDENT
    if publisher_a is not None and publisher_b is not None and publisher_a == publisher_b:
        return SourceIndependence.DEPENDENT
    if root_a is not None and root_b is not None and root_a == root_b:
        # Same corpus root is a weak dependency signal; if nothing else ties
        # them we stay UNKNOWN rather than over-claiming independence.
        return SourceIndependence.UNKNOWN
    if (
        document_a is not None
        and document_b is not None
        and document_a != document_b
        and source_a is not None
        and source_b is not None
        and source_a != source_b
    ):
        return SourceIndependence.INDEPENDENT
    return SourceIndependence.UNKNOWN
