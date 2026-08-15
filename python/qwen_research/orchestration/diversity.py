"""Source-diversity evaluation (single authoritative definition).

Reuses the Phase 5 source-independence subsystem (``SourceIdentity`` +
``assess_independence`` + ``count_independent_sources``) as the **one** source
of truth for source diversity. ``document_count`` and
``independent_source_count`` are kept distinct: only the latter may satisfy an
"independent sources" / "source diversity" / "corroboration" requirement.

Do not reimplement same-publisher / same-source / same-document / same-root
logic here — that lives in ``qwen_research/sources/independence.py``.
"""

from __future__ import annotations

import dataclasses

from qwen_research.sources.independence import SourceIdentity, count_independent_sources


@dataclasses.dataclass(frozen=True)
class SourceDiversity:
    """Two distinct metrics over an evidence set.

    ``document_count`` is the number of distinct documents represented (a raw,
    diagnostic count). ``independent_source_count`` is the Phase-5 semantic
    count and is the only value that satisfies an independent-source
    requirement.
    """

    document_count: int
    independent_source_count: int


def source_identities_from(evidence_identities: object) -> list[SourceIdentity]:
    """Reconstruct Phase-5 ``SourceIdentity`` values from persisted metadata.

    ``evidence_identities`` is the per-chunk metadata produced by the retrieval
    stage (a tuple/list of dicts with ``document_id`` / ``source_id`` /
    ``publisher`` / ``root_id``). Any missing field stays ``None`` (UNKNOWN) —
    never fabricated.
    """
    identities: list[SourceIdentity] = []
    if isinstance(evidence_identities, (list, tuple)):
        for entry in evidence_identities:
            if isinstance(entry, dict):
                identities.append(
                    SourceIdentity(
                        document_id=entry.get("document_id"),
                        source_id=entry.get("source_id"),
                        publisher=entry.get("publisher"),
                        root_id=entry.get("root_id"),
                    )
                )
    return identities


def evaluate_source_diversity(identities: list[SourceIdentity]) -> SourceDiversity:
    """Compute ``document_count`` and ``independent_source_count``.

    ``independent_source_count`` is derived by the Phase-5
    ``count_independent_sources`` function — the exact same calculation the
    verification/corroboration subsystem uses — so equivalent evidence sets
    always agree. ``document_count`` is diagnostic only and never satisfies an
    independent-source requirement.
    """
    document_count = len({i.document_id for i in identities if i.document_id is not None})
    independent_source_count = count_independent_sources(identities)
    return SourceDiversity(
        document_count=document_count,
        independent_source_count=independent_source_count,
    )


def source_diversity_from_outputs(outputs: dict[str, object]) -> SourceDiversity:
    """Convenience wrapper: evaluate diversity from persisted run outputs."""
    return evaluate_source_diversity(source_identities_from(outputs.get("evidence_identities")))
