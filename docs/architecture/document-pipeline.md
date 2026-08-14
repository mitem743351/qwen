# Document Pipeline

The document layer converts discovered files into normalized, searchable text
while preserving structure for citation. Parsers are **pluggable** via the
`DocumentParser` protocol.

```text
FileRecord → parser (by media type) → ParsedDocument → normalize → chunk → index
```

---

## Parser adapters

| Parser | Media types | Notes |
|--------|-------------|-------|
| `PlainTextParser` | `text/plain` | UTF-8 (with BOM); undecodable content is a parse **error**, never silently replaced |
| `MarkdownParser` | `text/markdown` | strips headers/fences; preserves headings as sections |
| `JsonParser` | `application/json` | flattens to `key: value` lines |
| `YamlParser` | `application/yaml` | via PyYAML (`safe_load`), falls back to raw text |
| `CodeParser` | python/rust/typescript/javascript/sql | indexed as normalized text |
| `CsvParser` | `text/csv` | rows rendered as `header: value` |
| `PdfParser` | `application/pdf` | per-page text; preserves page boundaries |

New document types are new parsers registered against a media type — the
pipeline is not redesigned.

---

## PDF handling

`pypdf` extracts per-page text; page boundaries are preserved as
`DocumentSection`s (page number + offsets) so citations can point at a page.
There is **no OCR**: a PDF with no extractable text returns
`ParseStatus.UNEXTRACTABLE` and remains discoverable as a document, rather than
silently producing an empty document.

---

## Normalization

Deterministic: CRLF/CR → LF, invalid control characters stripped, runs of
horizontal whitespace collapsed, trailing whitespace trimmed, blank-line runs
collapsed. Source fidelity is preferred over cosmetic cleanup.

---

## Chunking

A deterministic, structure-aware chunker packs paragraph boundaries first
(paragraph → sentence → hard split for oversized paragraphs) up to
`chunk_size` with `chunk_overlap` between adjacent chunks. Every chunk retains
`document_id`, `source_id`, page, section, and character offsets.

---

## Provenance

The raw source (immutable, content-hashed) → `Document` (metadata) →
`DocumentContent` (normalized text + sections) → `Chunk` (searchable span with
full provenance). Anonymous retrieved text is never produced.
