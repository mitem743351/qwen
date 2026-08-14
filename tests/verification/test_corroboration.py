"""Corroboration regression tests (source-independence based).

Corroboration must be judged at the *source* level using ``assess_independence``
(which collapses same-document, same-source, and same-publisher items), never by
merely counting distinct document ids.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.corpus.records import Document
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import RetrievedChunk
from qwen_research.verification.models import VerificationStatus
from qwen_research.verification.service import EvidenceIntegrityService
from qwen_research.verification.sqlite import SqliteVerificationStore


class _FakeCorpus:
    """A minimal corpus with explicit document metadata (incl. publisher)."""

    def __init__(self, documents: list[Document], chunks: dict[str, RetrievedChunk]) -> None:
        self._documents = documents
        self._chunks = chunks

    def list_documents(self) -> list[Document]:
        return list(self._documents)

    def get_chunks_for_ids(self, chunk_ids: list[str]) -> list[RetrievedChunk]:
        return [self._chunks[c] for c in chunk_ids if c in self._chunks]

    def list_stale_document_ids(self) -> set[str]:
        return set()


def _document(doc_id: str, src_id: str, publisher: str | None) -> Document:
    metadata = {"parse_status": "ok"}
    if publisher is not None:
        metadata["publisher"] = publisher
    return Document(
        document_id=doc_id,
        source_id=src_id,
        path=f"/{doc_id}.txt",
        root_id="root",
        relative_path=f"{doc_id}.txt",
        media_type="text/plain",
        title=doc_id,
        metadata=metadata,
        content_hash=f"hash-{doc_id}",
        size_bytes=1,
        modified_at=None,
    )


def _chunk(chunk_id: str, doc_id: str, src_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        source_id=src_id,
        text=f"supporting evidence {chunk_id}",
        score=0.9,
    )


def _service(
    tmp_path: Path, documents: list[Document], chunks: dict[str, RetrievedChunk]
) -> EvidenceIntegrityService:
    corpus = cast(CorpusIndex, _FakeCorpus(documents, chunks))
    store = SqliteVerificationStore(tmp_path / "verification.db")
    store.initialize()
    return EvidenceIntegrityService(store, corpus_index=corpus)


def test_same_publisher_is_not_independent_corroboration(tmp_path: Path) -> None:
    documents = [
        _document("doc1", "src1", "acme"),
        _document("doc2", "src2", "acme"),
    ]
    chunks = {
        "c1": _chunk("c1", "doc1", "src1"),
        "c2": _chunk("c2", "doc2", "src2"),
    }
    service = _service(tmp_path, documents, chunks)
    claim = service.create_claim("p", "claim supported by two acme pieces")
    service.link_claim_evidence("p", claim.claim_id, "c1", ClaimEvidenceRelationship.SUPPORTS)
    service.link_claim_evidence("p", claim.claim_id, "c2", ClaimEvidenceRelationship.SUPPORTS)

    report = service.verify_claim("p", claim.claim_id)

    # Same publisher → DEPENDENT → not independent corroboration.
    assert report.coverage.claims_with_independent_corroboration == 0
    assert report.status is VerificationStatus.SUPPORTED


def test_distinct_publishers_are_independent_corroboration(tmp_path: Path) -> None:
    documents = [
        _document("doc1", "src1", "acme"),
        _document("doc2", "src2", "beta"),
    ]
    chunks = {
        "c1": _chunk("c1", "doc1", "src1"),
        "c2": _chunk("c2", "doc2", "src2"),
    }
    service = _service(tmp_path, documents, chunks)
    claim = service.create_claim("p", "claim supported by two distinct publishers")
    service.link_claim_evidence("p", claim.claim_id, "c1", ClaimEvidenceRelationship.SUPPORTS)
    service.link_claim_evidence("p", claim.claim_id, "c2", ClaimEvidenceRelationship.SUPPORTS)

    report = service.verify_claim("p", claim.claim_id)

    assert report.coverage.claims_with_independent_corroboration == 1
    assert report.status is VerificationStatus.VERIFIED_WITHIN_CORPUS


def test_same_document_chunks_are_not_independent(tmp_path: Path) -> None:
    documents = [_document("doc1", "src1", "acme")]
    chunks = {
        "c1": _chunk("c1", "doc1", "src1"),
        "c2": _chunk("c2", "doc1", "src1"),
    }
    service = _service(tmp_path, documents, chunks)
    claim = service.create_claim("p", "claim supported by two chunks of one doc")
    service.link_claim_evidence("p", claim.claim_id, "c1", ClaimEvidenceRelationship.SUPPORTS)
    service.link_claim_evidence("p", claim.claim_id, "c2", ClaimEvidenceRelationship.SUPPORTS)

    report = service.verify_claim("p", claim.claim_id)

    assert report.coverage.claims_with_independent_corroboration == 0
    assert report.status is VerificationStatus.SUPPORTED
