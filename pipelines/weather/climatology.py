"""Builds cached daily climatological normals from the lake's own already-backfilled
Open-Meteo history (2018-present, written by pull_weather.py) via
core.seasonal.seasonal_stats -- never reimplemented, per CLAUDE.md rule 4 (2020 excluded
automatically by that function's own default years/exclude tuple).

No separate archive fetch here: an earlier version of this module made its own 2010-2024
archive call per city group, but confirmed live that a *second* large multi-year,
multi-city Open-Meteo call -- on top of the one pull_weather.py's own history backfill
already makes -- reliably trips the free tier's rate limit, even with proactive pacing.
Reusing the already-ingested lake history avoids that call entirely and is simpler.

Cached as a plain Parquet file with an mtime-staleness check, mirroring
pipelines/entsog/directory.py's own raw-cache pattern -- no DuckDB table involved,
core/storage.py has no precedent for a persisted non-ts_long table."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from core.seasonal import default_years, seasonal_stats
from core.storage import read_ts_long

CACHE_PATH = Path("data/raw/weather/climatology.parquet")
MAX_AGE_DAYS = 30
# core.seasonal's own window (2018 -> last complete year), not a literal range: this was
# hardcoded to `range(2018, 2026)`, which would have frozen the normals at 2018-2025 from
# 1 Jan 2027 onward. Resolved at import, which is enough here -- every caller is a
# pipeline script that runs and exits, not the long-lived Streamlit process.
CLIMATOLOGY_YEARS = default_years()


def _is_stale(cache_path: Path, max_age_days: int) -> bool:
    if not cache_path.exists():
        return True
    age_days = (time.time() - cache_path.stat().st_mtime) / 86400
    return age_days > max_age_days


def build_climatology(
    cache_path: Path = CACHE_PATH, max_age_days: int = MAX_AGE_DAYS
) -> pd.DataFrame:
    """Returns {series_id, doy, climatology} for every hdd.*/cdd.* series already in the
    lake -- per-city and the population-weighted eu/us aggregates alike. Reads only
    source="open_meteo" (real observations), never the ".forecast"-suffixed rows."""
    if not _is_stale(cache_path, max_age_days):
        return pd.read_parquet(cache_path)

    # source="open_meteo" narrows the parquet glob to that partition's own directory
    # (core/storage.py::_dataset_glob) before a single row is read, rather than
    # materialising the whole lake and filtering source in pandas afterward -- the
    # 17x-over-read fix (101,280 open_meteo rows out of 1,764,030 lake-wide). The
    # hdd./cdd. prefix filter stays in pandas: it selects *two* prefixes, and
    # read_ts_long's series_prefix only takes one, so two round trips to save an
    # in-memory filter over an already-narrowed ~100k-row frame would be a poor trade.
    long_df = read_ts_long(series_ids=None, source="open_meteo")
    long_df = long_df[long_df["series_id"].str.startswith(("hdd.", "cdd."))]

    frames = []
    for series_id, group in long_df.groupby("series_id"):
        stats = seasonal_stats(group, value_col="value", years=CLIMATOLOGY_YEARS)
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "doy": stats.index,
                    "climatology": stats["median"].to_numpy(),
                }
            )
        )
    if not frames:
        # No open_meteo history at all yet (e.g. a freshly-cloned repo or CI's own
        # empty lake) -- callers (apps/dashboard/pages/08_weather.py's own
        # _anomaly_series) already handle an empty-but-correctly-typed frame here,
        # so return one instead of letting pd.concat([]) raise on an empty list.
        result = pd.DataFrame(columns=["series_id", "doy", "climatology"])
        return result
    result = pd.concat(frames, ignore_index=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, index=False)
    return result
