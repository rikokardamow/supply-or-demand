"""Publish pipeline output into Supabase's serving.* schema (Spec 32).

The DuckDB/Parquet lake stays the system of record; this is a read-optimised serving
copy for the Next.js UI (Spec 33). Pipelines connect as the database owner through the
pooler connection string in `settings.supabase_db_url` -- the anon/authenticated roles
used by the web UI never write here (see Spec 32 §4 and the RLS policies applied in
`supabase/migrations/`).
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Final

import pandas as pd
import psycopg
import requests

from core.failures import describe_exception
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
        "events",
        "sanctions",
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
) -> int:
    """Upsert `df` into `serving.<table>` on `key`, then append a `publish_log` row.
    Returns the number of rows actually written -- 0 when the publish was skipped, so a
    caller's own log line cannot claim a publish that never happened.

    Chunked COPY-into-a-temp-table + `INSERT ... ON CONFLICT DO UPDATE` (Spec 32 §3).
    COPY has no bound on row count per chunk, unlike a parameterised multi-row INSERT,
    which would hit Postgres' ~65,535-parameter limit well before `chunk_size` rows for
    any table with more than a handful of columns.

    **Precondition: `df.columns` and `key` are identifiers, not data.** Row *values* go
    through COPY and through parameters, so they can never reach a SQL identifier
    position -- but column and key names are interpolated into the statement text, so
    callers must supply them as literals or from a canonical schema, never from row
    content. `_check_identifiers` below enforces this rather than leaving it implicit.
    """
    if table not in _ALLOWED_TABLES:
        raise UnknownServingTableError(
            f"{table!r} is not a whitelisted serving.* table ({sorted(_ALLOWED_TABLES)})"
        )
    _check_identifiers([*df.columns, *key])
    if df.empty:
        print(f"serving.{table}: empty frame, nothing published")
        return 0

    # An unset SUPABASE_DB_URL is a legitimate state, not a failure: CI never has one,
    # and neither does a machine that hasn't opted into the serving layer. Skipping
    # keeps those runs green. A url that IS set but fails to connect is the opposite
    # case -- that exception propagates, so a real Supabase outage surfaces as a
    # non-zero exit rather than a quietly missing publish (core/failures.py's rule).
    db_url = settings.supabase_db_url
    if not db_url:
        print(f"serving-layer publish skipped for {table}: SUPABASE_DB_URL not configured")
        return 0

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

    _revalidate(table)
    return len(df)


# The UI's ISR window (Spec 33's pages use `revalidate = 3600`) is the fallback; this
# hook is what makes a publish visible immediately.
REVALIDATE_TIMEOUT_SECONDS: Final = 10


def _revalidate(table: str) -> None:
    """Ask the web app to drop its cached copy of `table` (Spec 32 §3).

    Best-effort by design: the rows are already committed by the time this runs, and
    Spec 32 §3 is explicit that "failure to revalidate is logged, not raised -- ISR
    fallback covers it". Failing the pipeline here would turn a cosmetic cache delay into
    a red scheduled task. This is the one place in this module where swallowing an
    exception is right, and it still prints.

    Not configured is the normal state until a Vercel deployment exists, and is silent:
    warning on every publish about a deployment nobody has made yet is noise.
    """
    base = settings.vercel_url
    secret = settings.revalidate_secret
    if not base or not secret:
        return

    try:
        response = requests.post(
            f"{base.rstrip('/')}/api/revalidate",
            params={"tag": table},
            # The secret goes in a header, never the query string: URLs get logged by
            # proxies, CDNs and access logs; headers generally do not.
            headers={"x-revalidate-secret": secret},
            timeout=REVALIDATE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        # describe_exception, not str(exc): a requests error embeds the full URL, and
        # this one carries no credential today but the habit is what keeps it that way.
        print(f"revalidate hook failed for {table} (publish itself succeeded): "
              f"{describe_exception(exc)}")


# A plain lowercase SQL identifier. Anything else -- mixed case, a quote, whitespace, a
# reserved word spelled oddly -- either breaks the unquoted interpolation below or is not
# something this project's canonical schemas ever produce.
_IDENTIFIER_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")


def _check_identifiers(names: Iterable[str]) -> None:
    bad = sorted({name for name in names if not _IDENTIFIER_RE.fullmatch(str(name))})
    if bad:
        raise ValueError(
            f"not a plain SQL identifier: {bad}. Column and key names are interpolated"
            " into the statement text, so they must come from a literal or a canonical"
            " schema -- never from row content."
        )


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


def _today_doy() -> int:
    """Today's day-of-year on `core.seasonal`'s own normalised calendar.

    `REFERENCE_YEAR` (2001) is not a leap year, so `date(2028, 2, 29).replace(year=2001)`
    raises `ValueError: day is out of range for month`. `core.seasonal` never hits this
    because `_drop_leap_day` filters 29 February out before `_normalised_doy` sees it --
    but *today* arrives unfiltered. 29 February is clamped to the 28th, matching
    `_drop_leap_day`'s treatment of the day as not existing on this calendar.
    """
    today = date.today()
    if (today.month, today.day) == (2, 29):
        return date(REFERENCE_YEAR, 2, 28).timetuple().tm_yday
    return today.replace(year=REFERENCE_YEAR).timetuple().tm_yday


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
        return track.where(pd.Series(band.index <= _today_doy(), index=band.index))

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
    populated: list[pd.DataFrame] = []
    dropped: list[str] = []
    for series_id, sub in df.groupby("series_id", sort=True):
        rows = seasonal_rows(sub, series_id=str(series_id), unit=_first_unit(sub))
        if rows.empty:
            dropped.append(str(series_id))
        else:
            populated.append(rows)

    # A series that cannot form a band is a finding, not a non-event: publish() only
    # upserts, so the rows from its last successful publish stay in the anon-readable
    # table and the UI keeps drawing a stale `current` track against a live band. Naming
    # them here is what makes that visible at all.
    if dropped:
        print(f"serving.seasonal: no usable band for {len(dropped)} series: {sorted(dropped)}")

    if not populated:
        return pd.DataFrame(columns=list(SEASONAL_COLUMNS))
    return pd.concat(populated, ignore_index=True)


def _first_unit(sub: pd.DataFrame) -> str | None:
    """The series' unit, or None -- never the string "nan".

    `str(float("nan"))` is `"nan"`, which would publish a literal `unit = 'nan'` into an
    anon-readable column rather than a NULL.
    """
    if sub["unit"].empty:
        return None
    first = sub["unit"].iloc[0]
    return None if pd.isna(first) else str(first)
