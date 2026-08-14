"""Document parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.corpus.records import FileRecord, FileStatus, ParseStatus
from qwen_research.documents.code import CodeParser
from qwen_research.documents.csv import CsvParser
from qwen_research.documents.markdown import MarkdownParser
from qwen_research.documents.pdf import PdfParser
from qwen_research.documents.structured import JsonParser, YamlParser
from qwen_research.documents.text import PlainTextParser
from qwen_research.domain.errors import DocumentParseError


def _record(tmp_path: Path, name: str, media_type: str, content: bytes) -> FileRecord:
    f = tmp_path / name
    f.write_bytes(content)
    return FileRecord(
        path=str(f),
        root_id="r",
        relative_path=name,
        extension=f.suffix,
        media_type=media_type,
        size_bytes=len(content),
        modified_at=None,
        content_hash="h",
        status=FileStatus.NEW,
    )


def test_plain_text(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.txt", "text/plain", b"Hello  world\n\nsecond paragraph\r\n")
    parsed = PlainTextParser().parse(record)
    assert parsed.status is ParseStatus.OK
    assert "Hello world" in parsed.text
    assert "second paragraph" in parsed.text
    assert "\r" not in parsed.text


def test_markdown_strips_headers_and_keeps_content(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.md", "text/markdown", b"# Title\n\nBody text\n")
    parsed = MarkdownParser().parse(record)
    assert "Body text" in parsed.text
    assert "#" not in parsed.text


def test_markdown_preserves_headings_as_sections(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.md", "text/markdown", b"# Intro\n\nx\n\n## Method\n\ny\n")
    parsed = MarkdownParser().parse(record)
    headings = [s.heading for s in parsed.sections]
    assert "Intro" in headings
    assert "Method" in headings


def test_code_parser(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.py", "text/x-python", b"def f():\n    return 1\n")
    parsed = CodeParser().parse(record)
    assert "def f()" in parsed.text


def test_json_parser_flattens(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.json", "application/json", b'{"a": {"b": 1}}')
    parsed = JsonParser().parse(record)
    assert "a.b: 1" in parsed.text


def test_json_parser_rejects_malformed(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.json", "application/json", b"{not json")
    with pytest.raises(DocumentParseError):
        JsonParser().parse(record)


def test_csv_parser(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.csv", "text/csv", b"name,value\nx,1\ny,2\n")
    parsed = CsvParser().parse(record)
    assert "name: x" in parsed.text
    assert "value: 2" in parsed.text


def test_yaml_parser(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.yaml", "application/yaml", b"a:\n  b: 1\n")
    parsed = YamlParser().parse(record)
    assert "a.b: 1" in parsed.text


def test_pdf_extracts_text_with_pages(tmp_path: Path) -> None:
    from pathlib import Path

    pdf = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "sample.pdf"
    record = FileRecord(
        path=str(pdf),
        root_id="r",
        relative_path="sample.pdf",
        extension=".pdf",
        media_type="application/pdf",
        size_bytes=pdf.stat().st_size,
        modified_at=None,
        content_hash="h",
        status=FileStatus.NEW,
    )
    parsed = PdfParser().parse(record)
    assert parsed.status is ParseStatus.OK
    assert "quantum error correction" in parsed.text.lower()
    pages = [s.page for s in parsed.sections]
    assert 1 in pages
    assert 2 in pages


def test_pdf_unextractable_flagged(tmp_path: Path) -> None:
    from pathlib import Path

    pdf = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "unextractable.pdf"
    record = FileRecord(
        path=str(pdf),
        root_id="r",
        relative_path="unextractable.pdf",
        extension=".pdf",
        media_type="application/pdf",
        size_bytes=pdf.stat().st_size,
        modified_at=None,
        content_hash="h",
        status=FileStatus.NEW,
    )
    parsed = PdfParser().parse(record)
    assert parsed.status is ParseStatus.UNEXTRACTABLE
    assert parsed.text == ""


def test_plain_text_rejects_undecodable(tmp_path: Path) -> None:
    record = _record(tmp_path, "a.txt", "text/plain", b"\xff\xfe\x00\x01")
    with pytest.raises(DocumentParseError):
        PlainTextParser().parse(record)
