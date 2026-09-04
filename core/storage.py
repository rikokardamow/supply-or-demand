"""Parquet + DuckDB lake: write/read ts_long and flows datasets.

**Critical historical bug, fixed here (see root CLAUDE.md / this module's own git
history for the full incident)**: `read_parquet(glob, ...)` over a *heterogeneous* set
of files (one source's own files typed `value` as int64 -- `pipelines/opec_momr`'s
Baker Hughes rig counts, genuinely whole numbers -- while every other source's files
correctly used double) silently truncated the ENTIRE `value` column to int64 at the
*scan* level, before any SQL-level CAST could ever see the real value -- confirmed
live: FX rates all near 1.0 collapsed to exactly `1` project-wide, and this wasn't a
one-series bug, it corrupted `read_ts_long`/`warehouse()` reads of *every* series
whenever DuckDB's default (positional, first-file-wins) schema resolution picked the
narrower type. Fixed two ways, both needed: `read_parquet(..., union_by_name=true)`
makes DuckDB resolve columns *by name* across files and widen to a safe common type
(double) instead of truncating -- confirmed live this is the actual mechanism, an
outer `CAST` alone does nothing once the scan has already destroyed the value. The
explicit `CAST` in `_typed_select` is kept anyway as defense in depth (self-documents
the expected type, guards against a different kind of mismatch `union_by_name` might
not save on its own) alongside a write-side `.astype({"value": "float64"})` in
`write_ts_long`/`write_flows` so a future int-only source can't reintroduce this."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from core.schemas import (
    EVENTS_SCHEMA,
    FLOWS_SCHEMA,
    SANCTIONS_SCHEMA,
    TS_LONG_SCHEMA,
    validate_events,
    validate_flows,
    validate_sanctions,
    validate_ts_long,
)

LAKE_ROOT = Path("data/lake")


def _duckdb_type(pa_type: pa.DataType) -> str:
    if pa.types.is_string(pa_type):
        return "VARCHAR"
    if pa.types.is_timestamp(pa_type):
        return "TIMESTAMP"
    if pa.types.is_floating(pa_type):
        return "DOUBLE"
    if pa.types.is_integer(pa_type):
        return "BIGINT"
    if pa.types.is_list(pa_type):
        return f"{_duckdb_type(pa_type.value_type)}[]"
    raise ValueError(f"no DuckDB type mapping for pyarrow type {pa_type!r}")


def _available_columns(con: duckdb.DuckDBPyConnection, glob: str) -> set[str]:
    """Columns `union_by_name=true` can actually see across the glob's files. A schema
    column absent from EVERY on-disk file (e.g. a field added to a schema after those
    files were written -- confirmed live with `events.language`, added mid-project)
    isn't among these, and referencing it directly in the outer SELECT raises a DuckDB
    Binder Error ("Referenced column ... not found") -- `union_by_name` only NULL-fills
    a column present in at least *one* scanned file, not one present in *none*."""
    query = f"SELECT * FROM read_parquet('{glob}', union_by_name=true) LIMIT 0"
    return set(con.execute(query).df().columns)


def _typed_select(schema: pa.Schema, available: set[str]) -> str:
    """Every column explicitly cast to its canonical schema type -- never a bare
    `SELECT *` over a parquet glob, which lets DuckDB's own cross-file schema
    resolution silently pick the wrong type (see this module's own docstring). A
    schema column not in `available` (no on-disk file has it yet) is selected as a
    typed NULL literal instead of referencing it, so reading still works before the
    first write under the new schema lands."""
    parts = []
    for f in schema:
        db_type = _duckdb_type(f.type)
        if f.name in available:
            parts.append(f'CAST("{f.name}" AS {db_type}) AS "{f.name}"')
        else:
            parts.append(f'CAST(NULL AS {db_type}) AS "{f.name}"')
    return ", ".join(parts)


def _partition_dir(dataset: str, source: str, year: int) -> Path:
    return LAKE_ROOT / dataset / f"source={source}" / f"year={year}"


def _dataset_glob(dataset: str) -> str:
    return str(LAKE_ROOT / dataset / "**" / "*.parquet")


def _has_any_files(dataset: str) -> bool:
    return any((LAKE_ROOT / dataset).glob("**/*.parquet"))


def _normalise_datetime_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Some writers build timestamps via `datetime.now(UTC)` (tz-aware), others via
    `datetime.now()` (tz-naive) -- confirmed live this collides the moment both land in
    the same partition: pandas refuses to sort/compare a tz-aware Timestamp against a
    tz-naive one, so `_write_partitioned`'s own `combined.sort_values(sort_col)` raises
    `TypeError: Cannot compare tz-naive and tz-aware timestamps` the first time a
    tz-aware write lands in a partition that already has tz-naive rows (or vice versa).
    Every schema column here is stored as a plain (tz-naive) TIMESTAMP on disk (see
    `_duckdb_type` -- no TIMESTAMPTZ mapping exists), so this converts any tz-aware
    datetime column to UTC first (preserving the real instant) then drops the tzinfo,
    rather than guessing which writer's own convention is "right". Applied to each
    frame separately, before concatenation -- a mixed-tz column would already be
    object-dtype by the time the two frames are combined, which this dtype check can no
    longer see."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) and df[col].dt.tz is not None:
            df[col] = df[col].dt.tz_convert("UTC").dt.tz_localize(None)
    return df


def _write_partitioned(
    df: pd.DataFrame,
    dataset: str,
    source: str,
    dedup_subset: list[str] | None,
    sort_col: str | None,
    replace_window: tuple[datetime, datetime] | None = None,
) -> None:
    df = _normalise_datetime_tz(df)
    df["_year"] = df["ts"].dt.year

    for year, year_df in df.groupby("_year"):
        year_df = year_df.drop(columns="_year")
        partition_dir = _partition_dir(dataset, source, int(str(year)))
        partition_dir.mkdir(parents=True, exist_ok=True)

        existing_parts = sorted(partition_dir.glob("part-*.parquet"))
        existing_df = (
            _normalise_datetime_tz(
                pd.concat([pd.read_parquet(p) for p in existing_parts], ignore_index=True)
            )
            if existing_parts
            else pd.DataFrame(columns=year_df.columns)
        )
        if replace_window is not None and not existing_df.empty:
            window_start, window_end = replace_window
            in_window = (existing_df["ts"] >= window_start) & (existing_df["ts"] <= window_end)
            # Only replace rows for the (from_node, to_node) pairs actually present in
            # the fresh pull, not every pair the window has ever seen. Without this, a
            # pair that fails this run (a confirmed-live, routine occurrence — see
            # pipelines/entsog/CLAUDE.md and pipelines/entsoe/CLAUDE.md's per-item
            # resilience notes) has its still-good prior data deleted by this call and
            # replaced with nothing, silently losing real data for that pair — caught
            # live comparing two consecutive pull_daily.py runs where one border (
            # DE_LU->NL) failed on the second run only.
            if "from_node" in year_df.columns and "to_node" in year_df.columns:
                fresh_pairs = set(
                    zip(year_df["from_node"], year_df["to_node"], strict=True)
                )
                pair_in_fresh = pd.Series(
                    list(
                        zip(
                            existing_df["from_node"],
                            existing_df["to_node"],
                            strict=True,
                        )
                    ),
                    index=existing_df.index,
                ).map(lambda pair, pairs=fresh_pairs: pair in pairs)
                in_window &= pair_in_fresh
            existing_df = existing_df.loc[~in_window]
        combined = pd.concat([existing_df, year_df], ignore_index=True)

        if sort_col is not None:
            combined = combined.sort_values(sort_col)
        subset = dedup_subset if dedup_subset is not None else list(combined.columns)
        combined = combined.drop_duplicates(subset=subset, keep="last").reset_index(drop=True)

        for part in existing_parts:
            part.unlink()
        combined.to_parquet(partition_dir / "part-0.parquet", index=False)


def write_ts_long(df: pd.DataFrame, source: str) -> None:
    validate_ts_long(df)
    # Belt and braces alongside the read-side CAST fix above: a caller whose own
    # DataFrame happens to hold only whole-number values (confirmed live: exactly
    # what pipelines/opec_momr's Baker Hughes rig counts do) would otherwise write a
    # genuinely int64-typed parquet column, even though `value` is always meant to be
    # float64 per TS_LONG_SCHEMA -- validate_ts_long's own numeric-dtype check accepts
    # int64 as "numeric", so it doesn't catch this on its own.
    df = df.astype({"value": "float64"})
    _write_partitioned(
        df,
        dataset="ts_long",
        source=source,
        dedup_subset=["series_id", "ts"],
        sort_col="revision_date",
    )


def write_flows(
    df: pd.DataFrame,
    source: str,
    replace_window: tuple[datetime, datetime] | None = None,
) -> None:
    """`replace_window`: when given (start, end), existing rows in [start, end] for
    the (from_node, to_node) pairs present in `df` are dropped before the new rows are
    written. Needed for revision-window re-pulls — unlike ts_long, flows has no
    revision_date column, so plain full-row de-dup can't tell a revised value from a
    genuinely new row (they differ, so both would be kept, silently double-counting
    downstream). Pass the exact window just re-pulled so its stale rows are replaced
    outright instead. Scoped to `df`'s own pairs (not every pair the window has ever
    seen) so a pair whose fetch failed this run and is absent from `df` keeps its
    still-good prior data rather than being deleted with nothing to replace it —
    confirmed live comparing two consecutive pull_daily.py runs where one border
    failed on the second run only."""
    validate_flows(df)
    df = df.astype({"value": "float64"})  # see write_ts_long's identical note above
    _write_partitioned(
        df,
        dataset="flows",
        source=source,
        dedup_subset=None,
        sort_col=None,
        replace_window=replace_window,
    )


def write_events(df: pd.DataFrame, source: str) -> None:
    """`event_id` (a hash of the article URL) is the natural dedup key -- news articles
    have no revision_date concept like ts_long's re-published series values do."""
    validate_events(df)
    _write_partitioned(
        df,
        dataset="events",
        source=source,
        dedup_subset=["event_id"],
        sort_col="ts",
    )


SANCTIONS_CURRENT_PATH = LAKE_ROOT / "sanctions" / "current.parquet"


def write_sanctions_current(df: pd.DataFrame) -> None:
    """OFAC's SDN list is a current-state table (first_seen/last_seen/status already
    encode the diff history -- see pipelines/ofac/pull_ofac.py::compute_diff), not an
    accumulating time series like ts_long/flows/events -- doesn't fit
    _write_partitioned's source=X/year=Y shape, so this overwrites a single file
    instead. Always exactly one file, so no multi-file glob/union_by_name concern
    applies here -- a plain pd.read_parquet is enough on the read side."""
    validate_sanctions(df)
    SANCTIONS_CURRENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SANCTIONS_CURRENT_PATH, index=False)


def read_sanctions_current() -> pd.DataFrame:
    if not SANCTIONS_CURRENT_PATH.exists():
        empty: pd.DataFrame = SANCTIONS_SCHEMA.empty_table().to_pandas()
        return empty
    return pd.read_parquet(SANCTIONS_CURRENT_PATH)


def write_sanctions_snapshot(df: pd.DataFrame, pull_date: datetime) -> None:
    """Write-only daily audit archive (per specs/15_ofac-sanctions.md) -- OFAC gives
    no revision history of its own, so this preserves what was actually published on
    each pull date. Not read back anywhere in this spec's scope."""
    snapshot_dir = LAKE_ROOT / "sanctions_raw" / f"dt={pull_date.date().isoformat()}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(snapshot_dir / "part-0.parquet", index=False)


def _read(
    dataset: str,
    schema: pa.Schema,
    extra_clauses: list[str],
    params: list[object],
) -> pd.DataFrame:
    if not _has_any_files(dataset):
        empty: pd.DataFrame = schema.empty_table().to_pandas()
        return empty

    con = duckdb.connect()
    glob = _dataset_glob(dataset)
    available = _available_columns(con, glob)
    query = (
        f"SELECT {_typed_select(schema, available)} "
        f"FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)"
    )
    if extra_clauses:
        query += " WHERE " + " AND ".join(extra_clauses)
    return con.execute(query, params).df()


def read_ts_long(
    series_ids: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[object] = []

    if series_ids is not None:
        placeholders = ", ".join("?" for _ in series_ids)
        clauses.append(f"series_id IN ({placeholders})")
        params.extend(series_ids)
    if start is not None:
        clauses.append("ts >= ?")
        params.append(start)
    if end is not None:
        clauses.append("ts <= ?")
        params.append(end)

    return _read("ts_long", TS_LONG_SCHEMA, clauses, params)


def read_flows(
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[object] = []

    if source is not None:
        clauses.append("source = ?")
        params.append(source)
    if start is not None:
        clauses.append("ts >= ?")
        params.append(start)
    if end is not None:
        clauses.append("ts <= ?")
        params.append(end)

    return _read("flows", FLOWS_SCHEMA, clauses, params)


def read_events(
    start: datetime | None = None,
    end: datetime | None = None,
    commodity: str | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[object] = []

    if start is not None:
        clauses.append("ts >= ?")
        params.append(start)
    if end is not None:
        clauses.append("ts <= ?")
        params.append(end)
    if commodity is not None:
        clauses.append("commodity = ?")
        params.append(commodity)

    return _read("events", EVENTS_SCHEMA, clauses, params)


def _register_view(con: duckdb.DuckDBPyConnection, dataset: str, schema: pa.Schema) -> None:
    if _has_any_files(dataset):
        glob = _dataset_glob(dataset)
        available = _available_columns(con, glob)
        con.execute(
            f"CREATE OR REPLACE VIEW {dataset} AS "
            f"SELECT {_typed_select(schema, available)} "
            f"FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)"
        )
    else:
        empty = schema.empty_table().to_pandas()
        con.register(f"_{dataset}_empty", empty)
        con.execute(f"CREATE OR REPLACE VIEW {dataset} AS SELECT * FROM _{dataset}_empty")


def warehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    _register_view(con, "ts_long", TS_LONG_SCHEMA)
    _register_view(con, "flows", FLOWS_SCHEMA)
    _register_view(con, "events", EVENTS_SCHEMA)
    return con
