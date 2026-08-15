"""Controlled artifact storage for computation outputs.

Artifacts are written only inside a configured output/workspace root; there is
no arbitrary output path. Large results are persisted here and referenced by
id rather than returned inline through MCP.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from qwen_research.common.ids import new_id
from qwen_research.corpus.security import is_safe_relative
from qwen_research.domain.errors import ArtifactError, PathSecurityError

_ARTIFACT_EXTENSIONS = (".csv", ".json", ".txt", ".md", ".svg", ".png")


class ArtifactStore:
    """Write/read computation artifacts under a controlled root."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, relative: str) -> Path:
        if not is_safe_relative(relative):
            raise PathSecurityError("artifact path escapes output root")
        path = (self._root / relative).resolve()
        try:
            path.relative_to(self._root)
        except ValueError:
            raise PathSecurityError("artifact path escapes output root") from None
        return path

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def save_json(self, data: object, *, name: str | None = None) -> str:
        rel = self._new_name(name, ".json")
        self._ensure_root()
        path = self._resolve(rel)
        path.write_text(json.dumps(data, sort_keys=True, default=str))
        return rel

    def save_csv(
        self, columns: tuple[str, ...], rows: list[tuple], *, name: str | None = None
    ) -> str:
        rel = self._new_name(name, ".csv")
        self._ensure_root()
        path = self._resolve(rel)
        with path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            writer.writerows(rows)
        return rel

    def save_text(self, text: str, *, name: str | None = None, extension: str = ".txt") -> str:
        if extension not in _ARTIFACT_EXTENSIONS:
            raise ArtifactError(f"unsupported artifact extension {extension!r}")
        rel = self._new_name(name, extension)
        self._ensure_root()
        self._resolve(rel).write_text(text)
        return rel

    def write_parquet(self, con: Any, query: str, *, name: str | None = None) -> str:
        """Write a DuckDB query result to a Parquet artifact inside the root."""
        rel = self._new_name(name, ".parquet")
        self._ensure_root()
        target = self._resolve(rel)
        con.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(target)])
        return rel

    def _new_name(self, name: str | None, extension: str) -> str:
        if name is not None:
            if not is_safe_relative(name):
                raise PathSecurityError("artifact name escapes output root")
            if Path(name).suffix not in (extension, ""):
                raise ArtifactError(f"invalid artifact name {name!r}")
            return name if name.endswith(extension) else f"{name}{extension}"
        return f"{new_id('artifact')}{extension}"

    def read_text(self, relative: str) -> str:
        return self._resolve(relative).read_text()

    def path(self, relative: str) -> Path:
        return self._resolve(relative)
