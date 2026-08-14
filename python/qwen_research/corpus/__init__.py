"""Corpus layer: files, roots, discovery, hashing, and path security."""

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.corpus.hashing import hash_bytes, hash_file
from qwen_research.corpus.records import (
    Chunk,
    Document,
    DocumentContent,
    DocumentSection,
    FileRecord,
    FileStatus,
    ParseStatus,
)
from qwen_research.corpus.scanner import Scanner, ScanResult
from qwen_research.corpus.security import (
    is_safe_relative,
    resolve_file,
    resolve_root,
    resolve_within_root,
    validate_roots,
)

__all__ = [
    "Chunk",
    "CorpusConfig",
    "CorpusRoot",
    "Document",
    "DocumentContent",
    "DocumentSection",
    "FileRecord",
    "FileStatus",
    "ParseStatus",
    "ScanResult",
    "Scanner",
    "hash_bytes",
    "hash_file",
    "is_safe_relative",
    "resolve_file",
    "resolve_root",
    "resolve_within_root",
    "validate_roots",
]
