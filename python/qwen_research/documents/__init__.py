"""Document layer: parsing, normalization, and chunking.

Parsers are pluggable via the :class:`DocumentParser` protocol; they produce
:class:`ParsedDocument` (normalized text + structure), never touch the index.
"""

from qwen_research.documents.base import DocumentParser, ParsedDocument, parser_for
from qwen_research.documents.chunking import chunk_text
from qwen_research.documents.normalization import normalize_text

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "chunk_text",
    "normalize_text",
    "parser_for",
]
