"""Indexing tests: insert/update/stale/idempotency/rebuild."""

from __future__ import annotations

from pathlib import Path

from corpus_helpers import build_index, copy_fixture_corpus, fixture_config, index_fixture


def test_fixture_corpus_indexes(tmp_path: Path) -> None:
    index, manager, report, _, _ = index_fixture(tmp_path)
    stats = index.stats()
    assert stats.documents >= 6
    assert stats.chunks >= 1
    assert report.documents_indexed >= 6


def test_idempotent_indexing(tmp_path: Path) -> None:
    corpus = copy_fixture_corpus(tmp_path)
    config = fixture_config(corpus_path=corpus)
    index, manager = build_index(tmp_path, config)
    first = manager.index_all()
    second = manager.index_all()
    # Second run indexes nothing new and does not duplicate documents/chunks.
    assert second.documents_indexed == 0
    assert second.new == 0
    assert second.unchanged == first.documents_indexed
    assert index.stats().documents == first.documents_indexed


def test_modified_file_updates_content(tmp_path: Path) -> None:
    index, manager, report, _, corpus = index_fixture(tmp_path)
    docs_before = index.stats().documents
    chunks_before = index.stats().chunks

    paper = corpus / "paper.txt"
    paper.write_text("Completely new topic about magnetic monopoles.\n")
    second = manager.index_all()
    assert second.changed >= 1
    assert index.stats().documents == docs_before  # same logical document
    # Content was replaced, not duplicated.
    assert index.stats().chunks <= chunks_before + 1


def test_missing_file_marks_stale(tmp_path: Path) -> None:
    index, manager, report, _, corpus = index_fixture(tmp_path)
    before = index.stats().stale_documents
    (corpus / "sample.json").unlink()
    manager.index_all()
    assert index.stats().stale_documents == before + 1


def test_remove_stale_deletes(tmp_path: Path) -> None:
    index, manager, report, _, corpus = index_fixture(tmp_path)
    (corpus / "sample.json").unlink()
    manager.index_all()
    removed = manager.remove_stale()
    assert removed == 1
    assert index.stats().stale_documents == 0


def test_rebuild_from_scratch(tmp_path: Path) -> None:
    index, manager, report, _, _ = index_fixture(tmp_path)
    docs_before = index.stats().documents
    rebuild = manager.rebuild()
    assert rebuild.documents_indexed == docs_before
    assert index.stats().documents == docs_before


def test_inextractable_pdf_flagged(tmp_path: Path) -> None:
    index, manager, report, _, _ = index_fixture(tmp_path)
    assert report.unextractable == 1
    docs = index.list_documents()
    names = [d.relative_path for d in docs]
    assert any(n.endswith("unextractable.pdf") for n in names)


def test_document_id_stable_across_content_change(tmp_path: Path) -> None:
    index, manager, report, _, corpus = index_fixture(tmp_path)
    # Find paper.txt's document id.
    paper_doc = next(d for d in index.list_documents() if d.relative_path == "paper.txt")
    doc_id_before = paper_doc.document_id

    (corpus / "paper.txt").write_text("Changed content about graphene.\n")
    manager.index_all()

    paper_doc_after = next(d for d in index.list_documents() if d.relative_path == "paper.txt")
    assert paper_doc_after.document_id == doc_id_before  # stable identity
    assert paper_doc_after.content_hash != paper_doc.content_hash


def test_document_ids_not_raw_paths(tmp_path: Path) -> None:
    index, manager, report, _, _ = index_fixture(tmp_path)
    for doc in index.list_documents():
        assert doc.document_id.startswith("doc_")
        assert "/" not in doc.document_id
