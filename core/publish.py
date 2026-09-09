"""Publish pipeline output into Supabase's serving.* schema (Spec 32).

The DuckDB/Parquet lake stays the system of record; this is a read-optimised serving
copy for the Next.js UI (Spec 33). Pipelines connect as the database owner through the
pooler connection string in `settings.supabase_db_url` -- the anon/authenticated roles
used by the web UI never write here (see Spec 32 §4 and the RLS policies applied in
`supabase/migrations/`).
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Final

import pandas as pd
import psycopg

from core.settings import settings

DEFAULT_CHUNK_SIZE: Final = 50_000

# Every serving.* table this project may publish into (Spec 32 §2). publish() refuses
# anything outside this set -- a typo'd table name must fail loudly, never silently
# write to (or attempt to create) an unintended table.
_ALLOWED_TABLES: Final = frozenset(
    {
        "series_long",
        "seasonal",
        "flows",
        "vessel_latest",
        "grp_scores",
        "grp_components",
        "curve_settles",
        "spreads",
        "wpsr_lines",
    }
)


class UnknownServingTableError(ValueError):
    """Raised when publish() is asked to write to a table outside serving.* (Spec 32 §2)."""


def publish(
    table: str,
    df: pd.DataFrame,
    *,
    as_of: datetime,
    source_note: str,
    key: list[str],
    pipeline: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> None:
    """Upsert `df` into `serving.<table>` on `key`, then append a `publish_log` row.

    Chunked COPY-into-a-temp-table + `INSERT ... ON CONFLICT DO UPDATE` (Spec 32 §3).
    COPY has no bound on row count per chunk, unlike a parameterised multi-row INSERT,
    which would hit Postgres' ~65,535-parameter limit well before `chunk_size` rows for
    any table with more than a handful of columns.
    """
    if table not in _ALLOWED_TABLES:
        raise UnknownServingTableError(
            f"{table!r} is not a whitelisted serving.* table ({sorted(_ALLOWED_TABLES)})"
        )
    if df.empty:
        return

    # An unset SUPABASE_DB_URL is a legitimate state, not a failure: CI never has one,
    # and neither does a machine that hasn't opted into the serving layer. Skipping
    # keeps those runs green. A url that IS set but fails to connect is the opposite
    # case -- that exception propagates, so a real Supabase outage surfaces as a
    # non-zero exit rather than a quietly missing publish (core/failures.py's rule).
    db_url = settings.supabase_db_url
    if not db_url:
        print(f"serving-layer publish skipped for {table}: SUPABASE_DB_URL not configured")
        return

    # Postgres refuses an ON CONFLICT DO UPDATE whose own INSERT proposes the same
    # constrained key twice ("cannot affect row a second time"), and real source data
    # does contain such rows -- confirmed live 2026-09-09, the WPSR pull returned 10
    # rows in 5 duplicate (series_id, ts) groups, clustered at the EIA client's
    # 5,000-row pagination boundaries, every duplicate carrying an identical value.
    # core/storage.py's own `_write_partitioned` dedups the same way for the lake, so
    # the serving copy must not choke on data the lake accepts. `keep="last"` matches
    # `_write_partitioned`'s sort-then-keep-last contract: order the frame so the row
    # that should win comes last (by revision_date, where the table has one).
    deduped = df.drop_duplicates(subset=key, keep="last")
    if len(deduped) < len(df):
        print(f"serving.{table}: dropped {len(df) - len(deduped)} duplicate {key} row(s)")
    df = deduped

    columns = list(df.columns)
    # prepare_threshold=None disables psycopg3's automatic prepared statements, which
    # Supabase's transaction-mode pooler (port 6543, the connection mode Spec 32 §3
    # specifies for publishes) does not support -- psycopg would otherwise start
    # preparing after the 5th repeat of a statement and fail mid-run, not at connect.
    with psycopg.connect(db_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            for start in range(0, len(df), chunk_size):
                chunk = df.iloc[start : start + chunk_size]
                _upsert_chunk(cur, table, chunk, columns, key)
            cur.execute(
                "insert into serving.publish_log"
                " (table_name, as_of, source_note, row_count, pipeline)"
                " values (%s, %s, %s, %s, %s)",
                (table, as_of, source_note, len(df), pipeline),
            )
        conn.commit()


def _upsert_chunk(
    cur: psycopg.Cursor[Any],
    table: str,
    chunk: pd.DataFrame,
    columns: list[str],
    key: list[str],
) -> None:
    cur.execute(f"create temporary table _publish_staging (like serving.{table}) on commit drop")

    buf = io.StringIO()
    chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    col_list = ", ".join(columns)
    copy_sql = f"copy _publish_staging ({col_list}) from stdin with (format csv, null '\\N')"
    with cur.copy(copy_sql) as copy:
        copy.write(buf.read())

    update_cols = [c for c in columns if c not in key]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conflict_cols = ", ".join(key)
    cur.execute(
        f"insert into serving.{table} ({col_list})"
        f" select {col_list} from _publish_staging"
        f" on conflict ({conflict_cols}) do update set {set_clause}"
    )
    # Every chunk shares one transaction (the commit is at the end of publish()), so
    # `on commit drop` alone would leave the next chunk's CREATE hitting "relation
    # _publish_staging already exists". Drop it explicitly per chunk.
    cur.execute("drop table _publish_staging")
