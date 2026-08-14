"""Generate the PDF test fixtures (run once, committed as binary fixtures).

Produces:

- ``sample.pdf``  — two pages of extractable text about quantum error correction.
- ``unextractable.pdf`` — a single page with a drawn rectangle and no text,
  so ``extract_text()`` returns empty (exercises ``UNEXTRACTABLE``).

Uses only the Python standard library (hand-assembled PDF with a correct xref
table), so no OCR/reportlab dependency is introduced.
"""

from __future__ import annotations

from pathlib import Path


def _make_pdf(contents: list[bytes]) -> bytes:
    """Assemble a minimal PDF with the given page content streams."""
    objects: list[bytes] = []
    # 1: catalog, 2: pages, then per page: a page + its content stream,
    # finally the font.
    font_obj_num = 3 + 2 * len(contents)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(contents)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(contents)} >>".encode())

    for i, content in enumerate(contents):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/Contents {content_num} 0 R >>"
            ).encode()
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )

    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_pos}\n"
        "%%EOF\n"
    ).encode()
    return bytes(out)


def _text_page(text: str) -> bytes:
    esc = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return f"BT /F1 12 Tf 72 720 Td ({esc}) Tj ET".encode()


def _draw_page() -> bytes:
    return b"72 700 200 50 re S"


def main() -> None:
    here = Path(__file__).resolve().parent / "corpus"
    sample = _make_pdf(
        [
            _text_page(
                "Quantum error correction thresholds are central to fault tolerant "
                "quantum computing."
            ),
            _text_page(
                "The surface code achieves a high threshold using local stabilizer "
                "measurements."
            ),
        ]
    )
    unextractable = _make_pdf([_draw_page()])
    (here / "sample.pdf").write_bytes(sample)
    (here / "unextractable.pdf").write_bytes(unextractable)
    print(f"wrote {here / 'sample.pdf'} ({len(sample)} bytes)")
    print(f"wrote {here / 'unextractable.pdf'} ({len(unextractable)} bytes)")


if __name__ == "__main__":
    main()
