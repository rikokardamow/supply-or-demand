"""Publish pipeline output into Supabase's serving.* schema (Spec 32).

The DuckDB/Parquet lake stays the system of record; this is a read-optimised serving
copy for the Next.js UI (Spec 33). Pipelines connect as the database owner through the
pooler connection string in `settings.supabase_db_url` -- the anon/authenticated roles
used by the web UI never write here (see Spec 32 §4 and the RLS policies applied in
`supabase/migrations/`).
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Final

import pandas as pd
import psycopg

from core.seasonal import (
    FIRST_SEASONAL_YEAR,
    REFERENCE_YEAR,
    default_years,
    seasonal_stats,
)
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


# serving.seasonal's own column order (Spec 32 §2), used as the frame contract between
# seasonal_rows() below and publish("seasonal", ...).
SEASONAL_COLUMNS: Final = (
    "series_id",
    "doy",
    "band_min",
    "band_max",
    "median",
    "current",
    "prior",
    "years",
    "unit",
)


def seasonal_rows(df: pd.DataFrame, series_id: str, unit: str | None = None) -> pd.DataFrame:
    """`serving.seasonal` rows for one series: the band, plus this year's and last
    year's tracks against it.

    All the maths comes from `core.seasonal` -- golden rule 4 forbids reimplementing
    seasonal statistics anywhere else, and 2020 stays excluded because that is
    `seasonal_stats`'s own default.

    Two calls, deliberately, rather than one: the band (`band_min`/`band_max`/`median`)
    comes from `default_years()`, which stops *before* the current year, while `current`
    and `prior` are read from a second call whose window is stretched to include it.
    Folding the current year into the band would let this year's track move the very
    benchmark it is being measured against (see `core.seasonal.default_years`'s own
    docstring); reading its values from a separately-windowed call keeps the day-of-year
    alignment identical without polluting the band.
    """
    empty = pd.DataFrame(columns=list(SEASONAL_COLUMNS))
    if df.empty:
        return empty

    # core.seasonal reindexes a ts-indexed series onto a daily grid, which requires
    # unique timestamps -- a duplicate raises "cannot reindex on an axis with duplicate
    # labels". The lake never holds duplicates (write_ts_long dedups on series_id+ts),
    # but a caller passing a freshly *pulled* frame can: EIA's pagination returns a few
    # boundary rows twice, which took the WPSR seasonal publish down on 2026-09-09.
    # Cleaning the input here keeps core.seasonal -- shared by every dashboard page --
    # untouched.
    df = df.drop_duplicates(subset="ts", keep="last")

    band = seasonal_stats(df, value_col="value")
    if band.empty or band[["lo", "hi", "median"]].isna().all().all():
        return empty

    this_year = date.today().year
    extended = seasonal_stats(
        df, value_col="value", years=range(FIRST_SEASONAL_YEAR, this_year + 1)
    )

    def _year_track(year: int) -> pd.Series:
        if str(year) not in extended.columns:
            return pd.Series(pd.NA, index=band.index, dtype="Float64")
        return extended[str(year)].reindex(band.index).astype("Float64")

    def _current_track() -> pd.Series:
        """This year's track, blanked after today.

        `core.seasonal` forward-fills each year to daily, which is right for a complete
        year but fabricates the current one -- it carries today's value flat to 31
        December. `serving.seasonal.current` is specified as "null if not yet" (Spec 32
        §2), and a filled-forward tail would draw a fake projection across the UI's
        seasonal chart. Confirmed live 2026-09-09 before this guard existed: German
        storage read 54.75% at doy 300 and doy 365, both months away.
        """
        track = _year_track(this_year)
        today_doy = date.today().replace(year=REFERENCE_YEAR).timetuple().tm_yday
        return track.where(pd.Series(band.index <= today_doy, index=band.index))

    # Year columns carry a value only where that year actually reported, so counting
    # them per doy would vary along the curve. The band's own width is the honest
    # figure: how many years `seasonal_stats` was allowed to draw on.
    band_years = [y for y in default_years() if str(y) in band.columns]

    rows = pd.DataFrame(
        {
            "series_id": series_id,
            "doy": band.index.astype(int),
            "band_min": band["lo"].to_numpy(),
            "band_max": band["hi"].to_numpy(),
            "median": band["median"].to_numpy(),
            "current": _current_track().to_numpy(),
            "prior": _year_track(this_year - 1).to_numpy(),
            "years": len(band_years),
            "unit": unit,
        }
    )
    return rows[list(SEASONAL_COLUMNS)].reset_index(drop=True)


def seasonal_frame(df: pd.DataFrame) -> pd.DataFrame:
    """`serving.seasonal` rows for every series in a `ts_long`-shaped frame.

    A series with too little history to form a band contributes nothing rather than a
    block of NaN rows -- an empty band is not a finding, and publishing one would put a
    row on the UI's seasonal chart that says nothing.
    """
    frames = [
        seasonal_rows(
            sub,
            series_id=str(series_id),
            unit=None if sub["unit"].empty else str(sub["unit"].iloc[0]),
        )
        for series_id, sub in df.groupby("series_id", sort=True)
    ]
    populated = [f for f in frames if not f.empty]
    if not populated:
        return pd.DataFrame(columns=list(SEASONAL_COLUMNS))
    return pd.concat(populated, ignore_index=True)
