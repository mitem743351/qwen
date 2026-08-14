"""The Source domain object."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import SourceId, new_id
from qwen_research.common.serialization import serializable


class SourceType(StrEnum):
    """Kinds of citable source material."""

    DOCUMENT = "document"
    PAPER = "paper"
    BOOK = "book"
    NOTE = "note"
    DATASET = "dataset"
    WEB = "web"
    OTHER = "other"


@serializable
@dataclasses.dataclass(frozen=True)
class Source:
    """A source document or external source.

    ``content_hash`` anchors the source to an immutable version of its content;
    it is the contract only — no hashing or document parsing occurs in Phase 1.
    """

    source_id: SourceId
    uri: str
    title: str
    source_type: SourceType
    author: str | None = None
    publication_date: datetime | None = None
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    content_hash: str | None = None

    @classmethod
    def create(
        cls,
        uri: str,
        title: str,
        source_type: SourceType,
        *,
        author: str | None = None,
        publication_date: datetime | None = None,
        metadata: dict[str, str] | None = None,
        content_hash: str | None = None,
    ) -> Source:
        return cls(
            source_id=SourceId(new_id("source")),
            uri=uri,
            title=title,
            source_type=source_type,
            author=author,
            publication_date=publication_date,
            metadata=dict(metadata or {}),
            content_hash=content_hash,
        )
