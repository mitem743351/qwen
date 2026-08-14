"""Structured-data parser (JSON / YAML).

Produces a normalized, searchable rendering of the structure. Values are
flattened into ``key: value`` lines; YAML is converted to JSON first when
PyYAML is available, otherwise handled as plain text. Content is never
interpreted as instructions.
"""

from __future__ import annotations

import json

from qwen_research.corpus.records import FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.documents.text import read_text
from qwen_research.domain.errors import DocumentParseError


def _flatten(data: object, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, (dict, list)):
                lines.extend(_flatten(value, path))
            else:
                lines.append(f"{path}: {value}")
    elif isinstance(data, list):
        for i, value in enumerate(data):
            path = f"{prefix}[{i}]"
            if isinstance(value, (dict, list)):
                lines.extend(_flatten(value, path))
            else:
                lines.append(f"{path}: {value}")
    else:
        lines.append(f"{prefix}: {data}")
    return lines


class JsonParser:
    """Parses JSON files (``application/json``)."""

    media_types: tuple[str, ...] = ("application/json",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        text = read_text(file_record.path)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentParseError(f"invalid JSON: {exc}") from exc
        return ParsedDocument(
            text=normalize_text("\n".join(_flatten(data))),
            status=ParseStatus.OK,
        )


class YamlParser:
    """Parses YAML files (``application/yaml``).

    Uses PyYAML if available (converting to JSON-equivalent structures),
    otherwise indexes the raw text so YAML files remain discoverable without a
    hard dependency.
    """

    media_types: tuple[str, ...] = ("application/yaml",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        text = read_text(file_record.path)
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(text)
            return ParsedDocument(
                text=normalize_text("\n".join(_flatten(data))),
                status=ParseStatus.OK,
            )
        except ImportError:
            return ParsedDocument(text=normalize_text(text), status=ParseStatus.OK)
        except Exception as exc:  # noqa: BLE001 — YAML can raise many types
            raise DocumentParseError(f"invalid YAML: {exc}") from exc
