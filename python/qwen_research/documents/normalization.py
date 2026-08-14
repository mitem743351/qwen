"""Deterministic text normalization.

Handles line endings, repeated whitespace, and invalid control characters
without aggressively rewriting content — source fidelity is preferred over
cosmetic cleanup, because normalized text still drives citations.
"""

from __future__ import annotations

import re

#: Control characters to strip except tab/newline/carriage-return.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Collapse 3+ blank lines to at most 2 (preserve paragraph breaks).
_BLANK_LINES_RE = re.compile(r"\n[ \t]*\n[ \t]*\n+")
#: Collapse runs of 2+ horizontal whitespace to a single space within a line.
_WS_RE = re.compile(r"[ \t]{2,}")


def normalize_text(text: str) -> str:
    """Return a deterministically normalized copy of *text*.

    - normalize CRLF / CR to LF
    - strip invalid control characters (keeping tab)
    - normalize spaces/tabs within a line to single spaces where they are
      purely cosmetic (leading/trailing per line trimmed)
    - collapse runs of blank lines to a single blank line
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()
