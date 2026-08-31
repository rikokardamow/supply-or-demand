"""Session A's own entrypoint (specs/08_weather.md's Session C introduces a separate,
later pull_daily.py that also triggers ECMWF map rendering -- this script is scoped to
Open-Meteo weather data only, named so it won't collide with that).

Writes a real multi-year history backfill (2018-present -- needed for
core.seasonal.seasonal_stats' own default 2018-2026 band, confirmed live that Open-Meteo's
archive endpoint returns this fast, batched per EU/US city group) plus the next 16 days as
a distinctly tagged forecast: series_id suffixed ".forecast" and source
"open_meteo_forecast" so it never collides with a real-observation row for the same day
once one lands (write_ts_long partitions by source, so the two never compete for the same
(series_id, ts) dedup slot) -- the page reads both explicitly, as a solid history line and
a dashed forecast extension."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.weather.aggregate import population_weighted
from pipelines.weather.cities import load_cities
from pipelines.weather.client import GROUP_PACING_SECONDS, fetch_archive, fetch_forecast
from pipelines.weather.climatology import build_climatology
from pipelines.weather.degree_days import to_ts_long

HISTORY_START = date(2018, 1, 1)
FORECAST_DAYS = 16


def _mark_as_forecast(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["series_id"] = df["series_id"] + ".forecast"
    df["source"] = "open_meteo_forecast"
    return df


def main() -> None:
    cities_df = load_cities()
    ingested_at = pd.Timestamp(datetime.now(UTC))
    today = datetime.now(UTC).date()

    history_frames = []
    forecast_frames = []
    for i, (_base, group_cities) in enumerate(cities_df.groupby("base")):
        if i > 0:
            time.sleep(GROUP_PACING_SECONDS)
        history_daily = fetch_archive(group_cities, HISTORY_START, today)
        history_frames.append(to_ts_long(history_daily, group_cities, ingested_at))

        forecast_daily = fetch_forecast(group_cities, days=FORECAST_DAYS)
        forecast_frames.append(to_ts_long(forecast_daily, group_cities, ingested_at))

    history_long = pd.concat(history_frames, ignore_index=True)
    forecast_long = pd.concat(forecast_frames, ignore_index=True)

    history_popw = pd.concat(
        [population_weighted(history_long, cities_df, m, ingested_at) for m in ("hdd", "cdd")],
        ignore_index=True,
    )
    forecast_popw = pd.concat(
        [population_weighted(forecast_long, cities_df, m, ingested_at) for m in ("hdd", "cdd")],
        ignore_index=True,
    )

    write_ts_long(pd.concat([history_long, history_popw], ignore_index=True), source="open_meteo")
    write_ts_long(
        _mark_as_forecast(pd.concat([forecast_long, forecast_popw], ignore_index=True)),
        source="open_meteo_forecast",
    )

    build_climatology()  # ensures the cached climatology Parquet is fresh (reads the lake)

    print(
        f"wrote {len(history_long) + len(history_popw)} history rows, "
        f"{len(forecast_long) + len(forecast_popw)} forecast rows"
    )


if __name__ == "__main__":
    main()
