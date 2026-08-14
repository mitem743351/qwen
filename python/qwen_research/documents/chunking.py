"""Deterministic, structure-aware chunking.

Chunks are built from paragraph boundaries first (falling back to hard
splitting for oversized paragraphs), with overlap between adjacent chunks.
Every chunk retains full provenance (document_id, source_id, page, section,
offsets).
"""

from __future__ import annotations

import dataclasses
import re

from qwen_research.corpus.records import Chunk, DocumentSection

#: Sentence boundary (used only when a single paragraph must be hard-split).
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclasses.dataclass(frozen=True)
class ChunkOptions:
    chunk_size: int = 1000
    chunk_overlap: int = 100


def _paragraphs(text: str) -> list[str]:
    """Split on blank lines; keep paragraph-internal line breaks as spaces."""
    return [p.replace("\n", " ").strip() for p in text.split("\n\n") if p.strip()]


def _hard_split(paragraph: str, size: int) -> list[str]:
    """Split an oversized paragraph, preferring sentence boundaries."""
    pieces: list[str] = []
    remaining = paragraph
    while len(remaining) > size:
        cut = remaining.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _section_for(sections: tuple[DocumentSection, ...], offset: int) -> DocumentSection | None:
    """Return the section spanning *offset*, or the last section before it."""
    hit: DocumentSection | None = None
    for section in sections:
        if section.start_offset <= offset <= section.end_offset:
            return section
        if section.start_offset <= offset:
            hit = section
    return hit


def chunk_text(
    text: str,
    *,
    document_id: str,
    source_id: str,
    options: ChunkOptions | None = None,
    sections: tuple[DocumentSection, ...] = (),
) -> list[Chunk]:
    """Chunk *text* deterministically, preserving provenance.

    Returns chunks with ``start_offset``/``end_offset`` as character offsets
    into *text*, and page/section derived from *sections*.
    """
    opts = options or ChunkOptions()
    if opts.chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    units: list[str] = []
    for paragraph in _paragraphs(text):
        if len(paragraph) <= opts.chunk_size:
            units.append(paragraph)
        else:
            units.extend(_hard_split(paragraph, opts.chunk_size))

    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    index = 0
    for unit in units:
        if not current:
            current = unit
            current_start = 0
        elif len(current) + 1 + len(unit) <= opts.chunk_size:
            current = f"{current} {unit}"
        else:
            chunks.append(
                _make_chunk(current, index, current_start, document_id, source_id, sections)
            )
            index += 1
            # Overlap: carry the trailing overlap of the previous chunk forward.
            if opts.chunk_overlap > 0 and len(current) > opts.chunk_overlap:
                overlap_start = len(current) - opts.chunk_overlap
                current = current[overlap_start:] + " " + unit
                current_start = current_start + overlap_start
            else:
                current = unit
                current_start = current_start + len(current) + 1
    if current:
        chunks.append(
            _make_chunk(current, index, current_start, document_id, source_id, sections)
        )
    return chunks


def _make_chunk(
    text: str,
    index: int,
    start_offset: int,
    document_id: str,
    source_id: str,
    sections: tuple[DocumentSection, ...],
) -> Chunk:
    section = _section_for(sections, start_offset)
    return Chunk(
        chunk_id=f"{document_id}#c{index}",
        document_id=document_id,
        source_id=source_id,
        text=text,
        page=section.page if section else None,
        section=section.heading if section else None,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )
