"""Research-memory provenance validation.

Research-derived memory must reference *existing* sources, evidence, and claims.
Validation happens at the memory service boundary (not only at MCP) and runs
**before** the write commits — so a partially valid record is never persisted.

Reference scoping:

- ``source_refs`` / ``evidence_refs`` resolve against the **corpus** (global
  source and chunk ids — shared across projects).
- ``claim_refs`` resolve against **research-memory claim ids within the same
  project** — a claim id from project A must not validate in project B.

User/project-originated metadata (``origin=user``) is not subject to research
provenance validation.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING

from qwen_research.domain.errors import ProvenanceError

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.indexing.interface import CorpusIndex


class ReferenceKind(StrEnum):
    SOURCE = "source"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    COMPUTATION = "computation"


@dataclasses.dataclass(frozen=True)
class ProvenanceValidator:
    """Validates research-memory references.

    ``sources`` and ``evidence`` are corpus-global; ``claims`` and
    ``computations`` map a project id to that project's known ids.
    """

    sources: frozenset[str] = frozenset()
    evidence: frozenset[str] = frozenset()
    claims: Mapping[str, frozenset[str]] = dataclasses.field(default_factory=dict)
    computations: Mapping[str, frozenset[str]] = dataclasses.field(default_factory=dict)

    def resolve(self, project_id: str, kind: ReferenceKind, identifier: str) -> bool:
        if kind is ReferenceKind.SOURCE:
            return identifier in self.sources
        if kind is ReferenceKind.EVIDENCE:
            return identifier in self.evidence
        if kind is ReferenceKind.CLAIM:
            return identifier in self.claims.get(project_id, frozenset())
        if kind is ReferenceKind.COMPUTATION:
            return identifier in self.computations.get(project_id, frozenset())
        return False

    def validate(
        self,
        project_id: str,
        *,
        source_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        claim_refs: tuple[str, ...] = (),
        computation_refs: tuple[str, ...] = (),
    ) -> None:
        """Raise :class:`ProvenanceError` for the first unresolved reference."""
        for ref in source_refs:
            if not self.resolve(project_id, ReferenceKind.SOURCE, ref):
                raise ProvenanceError(ReferenceKind.SOURCE.value, ref)
        for ref in evidence_refs:
            if not self.resolve(project_id, ReferenceKind.EVIDENCE, ref):
                raise ProvenanceError(ReferenceKind.EVIDENCE.value, ref)
        for ref in claim_refs:
            if not self.resolve(project_id, ReferenceKind.CLAIM, ref):
                raise ProvenanceError(ReferenceKind.CLAIM.value, ref)
        for ref in computation_refs:
            if not self.resolve(project_id, ReferenceKind.COMPUTATION, ref):
                raise ProvenanceError(ReferenceKind.COMPUTATION.value, ref)


def validator_from_corpus(
    index: CorpusIndex,
    *,
    claims: Mapping[str, frozenset[str]] | None = None,
    computations: Mapping[str, frozenset[str]] | None = None,
) -> ProvenanceValidator:
    """Build a validator from a corpus index.

    ``sources`` are the corpus document source ids; ``evidence`` are the corpus
    chunk ids (the evidence granularity in this system). ``claims`` (per
    project) comes from a claim/research-memory store; ``computations`` (per
    project) comes from the computation store (Phase 6).
    """
    sources = frozenset(doc.source_id for doc in index.list_documents())
    evidence = frozenset(chunk.chunk_id for chunk in index.list_chunks())
    return ProvenanceValidator(
        sources=sources,
        evidence=evidence,
        claims=claims or {},
        computations=computations or {},
    )
