"""Parquet + DuckDB lake: write/read ts_long and flows datasets."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from core.schemas import FLOWS_SCHEMA, TS_LONG_SCHEMA, validate_flows, validate_ts_long

LAKE_ROOT = Path("data/lake")


def _partition_dir(dataset: str, source: str, year: int) -> Path:
    return LAKE_ROOT / dataset / f"source={source}" / f"year={year}"


def _dataset_glob(dataset: str) -> str:
    return str(LAKE_ROOT / dataset / "**" / "*.parquet")


def _has_any_files(dataset: str) -> bool:
    return any((LAKE_ROOT / dataset).glob("**/*.parquet"))


def _write_partitioned(
    df: pd.DataFrame,
    dataset: str,
    source: str,
    dedup_subset: list[str] | None,
    sort_col: str | None,
) -> None:
    df = df.copy()
    df["_year"] = df["ts"].dt.year

    for year, year_df in df.groupby("_year"):
        year_df = year_df.drop(columns="_year")
        partition_dir = _partition_dir(dataset, source, int(str(year)))
        partition_dir.mkdir(parents=True, exist_ok=True)

        existing_parts = sorted(partition_dir.glob("part-*.parquet"))
        existing_df = (
            pd.concat([pd.read_parquet(p) for p in existing_parts], ignore_index=True)
            if existing_parts
            else pd.DataFrame(columns=year_df.columns)
        )
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
    _write_partitioned(
        df,
        dataset="ts_long",
        source=source,
        dedup_subset=["series_id", "ts"],
        sort_col="revision_date",
    )


def write_flows(df: pd.DataFrame, source: str) -> None:
    validate_flows(df)
    _write_partitioned(df, dataset="flows", source=source, dedup_subset=None, sort_col=None)


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
    query = f"SELECT * FROM read_parquet('{glob}', hive_partitioning=false)"
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
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[object] = []

    if start is not None:
        clauses.append("ts >= ?")
        params.append(start)
    if end is not None:
        clauses.append("ts <= ?")
        params.append(end)

    return _read("flows", FLOWS_SCHEMA, clauses, params)


def _register_view(con: duckdb.DuckDBPyConnection, dataset: str, schema: pa.Schema) -> None:
    if _has_any_files(dataset):
        glob = _dataset_glob(dataset)
        con.execute(
            f"CREATE OR REPLACE VIEW {dataset} AS "
            f"SELECT * FROM read_parquet('{glob}', hive_partitioning=false)"
        )
    else:
        empty = schema.empty_table().to_pandas()
        con.register(f"_{dataset}_empty", empty)
        con.execute(f"CREATE OR REPLACE VIEW {dataset} AS SELECT * FROM _{dataset}_empty")


def warehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    _register_view(con, "ts_long", TS_LONG_SCHEMA)
    _register_view(con, "flows", FLOWS_SCHEMA)
    return con
