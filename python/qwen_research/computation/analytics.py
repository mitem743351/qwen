"""DuckDB analytics engine.

DuckDB is the analytical engine; it is never exposed to the Research Runtime
as a raw connection. SQL lives only inside this module. Queries operate
against explicit, controlled, in-memory sessions whose tables are loaded from
*resolved* (corpus-security-checked) dataset files; user SQL runs with DuckDB
``enable_external_access = false`` plus statement validation, so it cannot
``ATTACH``, ``COPY``, ``INSTALL``/``LOAD`` extensions, or read arbitrary
filesystem paths.
"""

from __future__ import annotations

import re
import sqlite3 as _sqlite3
from dataclasses import dataclass
from typing import Any

from qwen_research.computation.datasets import ResolvedDataset
from qwen_research.computation.models import ColumnProfile, DatasetProfile
from qwen_research.domain.errors import (
    DatasetError,
    QueryValidationError,
    ResourceLimitError,
)

#: Statement prefixes that must never reach DuckDB from user input.
_FORBIDDEN = (
    "attach",
    "detach",
    "copy",
    "export",
    "import",
    "install",
    "load",
    "pragma",
    "call",
    "set",
    "read_csv",
    "read_parquet",
    "read_json",
    "read_text",
    "read_blob",
    "glob(",
    "sqlite_scan",
    "sqlite_attach",
    "parquet_scan",
    "httpfs",
    "secret",
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_sql(query: str) -> str:
    """Validate and normalize a single SQL statement.

    Rejects multi-statement input and any forbidden clause/function. Returns
    the query with a single trailing semicolon stripped.
    """
    text = query.strip()
    if not text:
        raise QueryValidationError("empty query")
    lowered = text.lower()
    for token in _FORBIDDEN:
        if token in lowered:
            raise QueryValidationError(f"query uses disallowed construct {token!r}")
    # Single statement only: allow one trailing semicolon, reject the rest.
    stripped = text[:-1] if text.endswith(";") else text
    if ";" in stripped:
        raise QueryValidationError("multiple statements are not allowed")
    return stripped


def validate_identifier(name: str) -> str:
    """Validate a table/column identifier against a strict pattern."""
    if not _IDENT_RE.match(name):
        raise QueryValidationError(f"invalid identifier {name!r}")
    return name


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _parameter_order(sql: str) -> list[str]:
    """Return positional ``:name`` parameter references in first-appearance order."""
    return re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", sql)


@dataclass(frozen=True)
class TableResult:
    """A bounded tabular result."""

    columns: tuple[str, ...]
    rows: list[tuple]
    row_count: int
    truncated: bool


class DuckDBBackend:
    """DuckDB implementation of the analytical engine.

    Each call opens a fresh in-memory database, loads the approved datasets
    into safely-named tables, disables external access, and then runs the
    (validated) query. No connection or raw file path escapes this object.
    """

    def __init__(self) -> None:
        try:
            import duckdb  # noqa: F401 — imported to fail fast with a clear error
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise DatasetError("duckdb is not installed") from exc

    # -- public ------------------------------------------------------------

    def describe_dataset(self, resolved: ResolvedDataset, *, max_rows: int) -> DatasetProfile:
        con = self._open()
        table = self._load(con, [resolved])["t0"]
        return self._profile(con, table, resolved)

    def run_query(
        self,
        datasets: list[ResolvedDataset],
        query: str,
        parameters: dict[str, object],
        *,
        max_rows: int,
        max_output_bytes: int,
    ) -> TableResult:
        con = self._open()
        self._load(con, datasets)
        sql = validate_sql(query)
        # Translate ``:name`` placeholders to DuckDB's positional ``?``.
        order = _parameter_order(sql)
        positional = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "?", sql)
        params = [parameters.get(k) for k in order]
        return self._execute(
            con, positional, params, max_rows=max_rows, max_output_bytes=max_output_bytes
        )

    def count(self, datasets: list[ResolvedDataset], *, max_rows: int) -> TableResult:
        con = self._open()
        table = self._load(con, datasets)["t0"]
        return self._execute(con, f"SELECT count(*) AS count FROM {table}", [], max_rows)

    def aggregate(
        self,
        datasets: list[ResolvedDataset],
        column: str,
        function: str,
        *,
        max_rows: int,
    ) -> TableResult:
        validate_identifier(column)
        agg = _normalize_aggregate(function)
        expr = "count(*)" if agg == "count" else f"{agg}({_quote(column)})"
        con = self._open()
        table = self._load(con, datasets)["t0"]
        return self._execute(con, f"SELECT {expr} AS value FROM {table}", [], max_rows)

    def group(
        self,
        datasets: list[ResolvedDataset],
        group_by: str,
        column: str,
        function: str,
        *,
        max_rows: int,
    ) -> TableResult:
        validate_identifier(group_by)
        validate_identifier(column)
        agg = _normalize_aggregate(function)
        expr = "count(*)" if agg == "count" else f"{agg}({_quote(column)})"
        con = self._open()
        table = self._load(con, datasets)["t0"]
        sql = (
            f"SELECT {_quote(group_by)}, {expr} AS value FROM {table} "
            f"GROUP BY {_quote(group_by)} ORDER BY {_quote(group_by)}"
        )
        return self._execute(con, sql, [], max_rows)

    def filter(
        self,
        datasets: list[ResolvedDataset],
        predicate: str,
        *,
        max_rows: int,
    ) -> TableResult:
        con = self._open()
        table = self._load(con, datasets)["t0"]
        sql = validate_sql(f"SELECT * FROM {table} WHERE {predicate}")
        return self._execute(con, sql, [], max_rows)

    def join(
        self,
        datasets: list[ResolvedDataset],
        left_key: str,
        right_key: str,
        *,
        max_rows: int,
    ) -> TableResult:
        if len(datasets) != 2:
            raise QueryValidationError("join requires exactly two datasets")
        validate_identifier(left_key)
        validate_identifier(right_key)
        con = self._open()
        names = self._load(con, datasets)
        left, right = names["t0"], names["t1"]
        sql = (
            f"SELECT * FROM {left} JOIN {right} "
            f"ON {left}.{_quote(left_key)} = {right}.{_quote(right_key)}"
        )
        return self._execute(con, sql, [], max_rows)

    def numeric_column(
        self, datasets: list[ResolvedDataset], column: str, *, max_rows: int
    ) -> list[float]:
        validate_identifier(column)
        con = self._open()
        table = self._load(con, datasets)["t0"]
        result = self._execute(con, f"SELECT {_quote(column)} FROM {table}", [], max_rows=max_rows)
        values: list[float] = []
        for row in result.rows:
            v = row[0]
            if v is None:
                values.append(float("nan"))
            else:
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    values.append(float("nan"))
        return values

    # -- internals ---------------------------------------------------------

    def _open(self) -> Any:
        import duckdb

        return duckdb.connect(":memory:")

    def _load(self, con: Any, datasets: list[ResolvedDataset]) -> dict[str, str]:
        """Load datasets into safely-named tables; return ``{alias: table}``."""
        names: dict[str, str] = {}
        for i, ds in enumerate(datasets):
            table = f"t{i}"
            if ds.format == "csv":
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?)", [ds.path])
            elif ds.format == "json":
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_json_auto(?)", [ds.path])
            elif ds.format == "parquet":
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet(?)", [ds.path])
            elif ds.format == "sqlite":
                self._load_sqlite(con, ds.path, table)
            else:
                raise DatasetError(f"unsupported dataset format {ds.format!r}")
            names[f"t{i}"] = table
        con.execute("SET enable_external_access=false")
        return names

    def _load_sqlite(self, con: Any, path: str, table: str) -> None:
        """Load a table from a SQLite database via the stdlib driver."""
        src = _sqlite3.connect(path)
        try:
            table_rows = src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not table_rows:
                raise DatasetError(f"sqlite dataset {path!r} has no tables")
            target = table_rows[0][0]
            info = src.execute(f"PRAGMA table_info({_quote(target)})").fetchall()
            cur = src.execute(f"SELECT * FROM {_quote(target)}")
            rows = list(cur)
        finally:
            src.close()
        cols = [d[0] for d in (cur.description or [])]
        if not cols:
            raise DatasetError(f"sqlite dataset {path!r} table {target!r} has no columns")
        col_defs = ", ".join(
            f"{_quote(c)} {_sqlite_duckdb_type(d[2])}" for c, d in zip(cols, info, strict=True)
        )
        con.execute(f"CREATE TABLE {table} ({col_defs})")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' for _ in cols)})", rows)

    def _profile(self, con: Any, table: str, resolved: ResolvedDataset) -> DatasetProfile:
        columns = con.execute(f"DESCRIBE {table}").fetchall()
        row_count = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        col_profiles: list[ColumnProfile] = []
        total_missing = 0
        for col_name, col_type, *_rest in columns:
            missing = row_count - int(
                con.execute(f"SELECT count({_quote(col_name)}) FROM {table}").fetchone()[0]
            )
            total_missing += missing
            distinct = int(
                con.execute(f"SELECT count(DISTINCT {_quote(col_name)}) FROM {table}").fetchone()[0]
            )
            lo = con.execute(f"SELECT min({_quote(col_name)}) FROM {table}").fetchone()[0]
            hi = con.execute(f"SELECT max({_quote(col_name)}) FROM {table}").fetchone()[0]
            col_profiles.append(
                ColumnProfile(
                    name=str(col_name),
                    data_type=str(col_type),
                    null_count=int(missing),
                    distinct_count=int(distinct),
                    min_value=None if lo is None else str(lo),
                    max_value=None if hi is None else str(hi),
                )
            )
        distinct_rows = int(
            con.execute(f"SELECT count(*) FROM (SELECT DISTINCT * FROM {table})").fetchone()[0]
        )
        duplicate_rows = max(0, row_count - distinct_rows)
        return DatasetProfile(
            dataset_id=resolved.dataset_id,
            row_count=row_count,
            column_count=len(columns),
            columns=tuple(col_profiles),
            size_bytes=resolved.size_bytes,
            content_hash=resolved.content_hash,
            missing_value_count=total_missing,
            duplicate_row_count=duplicate_rows,
        )

    def _execute(
        self,
        con: Any,
        sql: str,
        params: list,
        max_rows: int,
        max_output_bytes: int = 256 * 1024,
    ) -> TableResult:
        cur = con.execute(sql, params)
        cols = [d[0] for d in (cur.description or [])]
        rows: list[tuple] = []
        row_count = 0
        truncated = False
        output_bytes = 0
        for row in cur.fetchmany(max_rows + 1):
            if len(rows) >= max_rows:
                truncated = True
                break
            rows.append(tuple(row))
            row_count += 1
            output_bytes += sum(len(str(v)) for v in row)
            if output_bytes > max_output_bytes:
                raise ResourceLimitError(f"query output exceeded {max_output_bytes} bytes")
        return TableResult(
            columns=tuple(str(c) for c in cols),
            rows=rows,
            row_count=row_count,
            truncated=truncated,
        )


def _normalize_aggregate(function: str) -> str:
    fn = function.lower()
    if fn in ("sum", "mean", "avg", "min", "max", "count", "stddev", "variance", "median"):
        return "avg" if fn == "mean" else fn
    raise QueryValidationError(f"unsupported aggregate function {function!r}")


def _sqlite_duckdb_type(declared: object) -> str:
    """Map a SQLite declared column type to a DuckDB type."""
    text = str(declared).upper()
    if "INT" in text:
        return "BIGINT"
    if "REAL" in text or "FLOA" in text or "DOUB" in text or "NUM" in text:
        return "DOUBLE"
    if "BLOB" in text:
        return "BLOB"
    if "CHAR" in text or "CLOB" in text or "TEXT" in text:
        return "VARCHAR"
    return "VARCHAR"
