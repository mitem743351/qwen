"""Chunking tests: size limits, overlap, boundaries, provenance."""

from __future__ import annotations

from qwen_research.corpus.records import DocumentSection
from qwen_research.documents.chunking import ChunkOptions, chunk_text


def test_single_short_paragraph_is_one_chunk() -> None:
    chunks = chunk_text(
        "A single paragraph.",
        document_id="d1",
        source_id="s1",
        options=ChunkOptions(chunk_size=1000, chunk_overlap=0),
    )
    assert len(chunks) == 1
    assert chunks[0].text == "A single paragraph."


def test_multiple_paragraphs_pack_respecting_size() -> None:
    text = "word " * 300 + "\n\n" + "word " * 300
    chunks = chunk_text(
        text, document_id="d1", source_id="s1",
        options=ChunkOptions(chunk_size=500, chunk_overlap=0),
    )
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.text) <= 600  # one hard-split unit may exceed slightly


def test_provenance_preserved() -> None:
    text = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_text(text, document_id="d1", source_id="s1")
    for chunk in chunks:
        assert chunk.document_id == "d1"
        assert chunk.source_id == "s1"
        assert chunk.chunk_id.startswith("d1#c")


def test_page_and_section_from_sections() -> None:
    sections = (
        DocumentSection(
            section_id="s1", document_id="d1", page=1, heading="Intro",
            start_offset=0, end_offset=50,
        ),
        DocumentSection(
            section_id="s2", document_id="d1", page=2, heading="Method",
            start_offset=51, end_offset=200,
        ),
    )
    chunks = chunk_text(
        "x" * 120,
        document_id="d1",
        source_id="s1",
        sections=sections,
        options=ChunkOptions(chunk_size=1000, chunk_overlap=0),
    )
    # The single chunk starts at offset 0, which is in section "Intro" (page 1).
    assert chunks[0].page == 1
    assert chunks[0].section == "Intro"


def test_overlap_is_bounded() -> None:
    text = " ".join(f"paragraph{i}" for i in range(50))
    chunks = chunk_text(
        text,
        document_id="d1",
        source_id="s1",
        options=ChunkOptions(chunk_size=80, chunk_overlap=20),
    )
    assert len(chunks) >= 2
    # Overlap text should be present across adjacent chunks.
    assert chunks[0].text[-20:] in chunks[1].text


def test_offsets_are_consistent() -> None:
    text = "Alpha beta gamma.\n\nDelta epsilon."
    chunks = chunk_text(text, document_id="d1", source_id="s1")
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset > chunks[0].start_offset
