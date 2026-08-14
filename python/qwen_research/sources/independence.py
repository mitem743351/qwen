"""Source-independence heuristic.

Determines whether two evidence items come from independent sources. This is a
**basic heuristic** over available metadata (document, source, publisher, corpus
root) — it does not claim actual editorial independence.
"""

from __future__ import annotations

import dataclasses
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
    """Return INDEPENDENT / DEPENDENT / UNKNOWN for two evidence items.

    Order matters: a hard identity tie (same document / source / publisher)
    makes items DEPENDENT, and two *distinct* documents with *distinct* sources
    are INDEPENDENT even when they live under the same corpus root (the normal
    "two different papers in one corpus" case). A shared root is only a weak
    signal, consulted last — it downgrades undecidable cases to UNKNOWN rather
    than over-claiming independence.
    """
    if document_a is not None and document_a == document_b:
        return SourceIndependence.DEPENDENT
    if source_a is not None and source_a == source_b:
        return SourceIndependence.DEPENDENT
    if publisher_a is not None and publisher_b is not None and publisher_a == publisher_b:
        return SourceIndependence.DEPENDENT
    if (
        document_a is not None
        and document_b is not None
        and document_a != document_b
        and source_a is not None
        and source_b is not None
        and source_a != source_b
    ):
        return SourceIndependence.INDEPENDENT
    if root_a is not None and root_b is not None and root_a == root_b:
        # Same corpus root, but documents/sources are not fully distinguishable:
        # stay UNKNOWN rather than over-claiming independence.
        return SourceIndependence.UNKNOWN
    return SourceIndependence.UNKNOWN


@dataclasses.dataclass(frozen=True)
class SourceIdentity:
    """The provenance fields needed to judge independence between two items."""

    document_id: str | None
    source_id: str | None
    publisher: str | None
    root_id: str | None


def count_independent_sources(identities: list[SourceIdentity]) -> int:
    """Count independent source groups among evidence identities.

    Items joined by a ``DEPENDENT`` relationship (same document, same source,
    or same publisher) collapse into a single source group (transitively, via
    union-find). INDEPENDENT and UNKNOWN pairs stay separate. The returned
    count is the number of connected components of the DEPENDENT graph.
    """
    n = len(identities)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            rel = assess_independence(
                document_a=identities[i].document_id,
                document_b=identities[j].document_id,
                source_a=identities[i].source_id,
                source_b=identities[j].source_id,
                publisher_a=identities[i].publisher,
                publisher_b=identities[j].publisher,
                root_a=identities[i].root_id,
                root_b=identities[j].root_id,
            )
            if rel is SourceIndependence.DEPENDENT:
                union(i, j)

    return len({find(i) for i in range(n)})
