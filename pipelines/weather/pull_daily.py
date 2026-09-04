"""Session C's daily incremental entrypoint (Spec 13 orchestration), distinct from
pull_weather.py's one-off multi-year history backfill: refreshes the 16-day Open-Meteo
forecast (HDD/CDD for the 14 cities + pop-weighted aggregates, plus the DE/DK/IE wind
index), re-renders the 4 ECMWF anomaly maps, and (since the weather-module-spec.md
Phase 1 session) pulls the same two things from GFS -- 2 anomaly maps (D+3 only, EU/
CONUS) and GFS-sourced HDD/CDD aggregates. write_ts_long's own (series_id, ts) de-dup
(keep latest revision_date) makes a daily re-pull of an overlapping forecast window
naturally idempotent, same reasoning as pipelines/entsoe/pull_daily.py's prices/load/
generation re-pulls needing no extra revision-window logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.weather.aggregate import population_weighted
from pipelines.weather.anomaly_maps import render_anomaly_map
from pipelines.weather.cities import load_cities
from pipelines.weather.client import fetch_forecast
from pipelines.weather.climatology_grid import REGION_BOUNDS
from pipelines.weather.degree_days import to_ts_long
from pipelines.weather.ecmwf_client import fetch_2t_forecast, load_2t_dataset
from pipelines.weather.gfs_client import FORECAST_STEP_HOURS as GFS_STEP_HOURS
from pipelines.weather.gfs_client import (
    fetch_2t_forecast as fetch_gfs_2t_forecast,
)
from pipelines.weather.gfs_client import (
    load_2t_dataset as load_gfs_2t_dataset,
)
from pipelines.weather.gfs_client import valid_time_for as gfs_valid_time_for
from pipelines.weather.gfs_degree_days import sample_cities as sample_gfs_cities
from pipelines.weather.wind import load_wind_locations, wind_forecast_to_ts_long

FORECAST_DAYS = 16


def _mark_as_forecast(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["series_id"] = df["series_id"] + ".forecast"
    df["source"] = "open_meteo_forecast"
    return df


def pull_hdd_cdd_forecast(ingested_at: pd.Timestamp) -> pd.DataFrame:
    cities_df = load_cities()
    forecast_frames = []
    for _base, group_cities in cities_df.groupby("base"):
        daily = fetch_forecast(group_cities, days=FORECAST_DAYS)
        forecast_frames.append(to_ts_long(daily, group_cities, ingested_at))

    forecast_long = pd.concat(forecast_frames, ignore_index=True)
    forecast_popw = pd.concat(
        [population_weighted(forecast_long, cities_df, m, ingested_at) for m in ("hdd", "cdd")],
        ignore_index=True,
    )
    return pd.concat([forecast_long, forecast_popw], ignore_index=True)


def pull_wind_forecast(ingested_at: pd.Timestamp) -> pd.DataFrame:
    locations_df = load_wind_locations()
    daily = fetch_forecast(locations_df, days=FORECAST_DAYS)
    return wind_forecast_to_ts_long(daily, locations_df, ingested_at)


def render_daily_anomaly_maps() -> list[str]:
    path = fetch_2t_forecast()
    ds = load_2t_dataset(path)
    t2m = ds["t2m"]

    rendered = []
    for region in REGION_BOUNDS:
        for step_index in range(t2m.sizes["step"]):
            step_slice = t2m.isel(step=step_index)
            step_hours = int(step_slice.step.values / pd.Timedelta(hours=1))
            valid_time = pd.Timestamp(step_slice.valid_time.values)
            rendered.append(
                str(
                    render_anomaly_map(
                        step_slice,
                        step_hours=step_hours,
                        valid_time=valid_time,
                        region=region,
                        model="ecmwf",
                    )
                )
            )
    return rendered


def render_gfs_anomaly_maps() -> list[str]:
    """D+3 only for Phase 1 (GFS_STEP_HOURS' own default) -- matches this pipeline's
    own session-sized-scope precedent; D+7 is a natural follow-on once this is proven."""
    rendered = []
    for region in REGION_BOUNDS:
        path, _run = fetch_gfs_2t_forecast(region, step_hours=GFS_STEP_HOURS)
        ds = load_gfs_2t_dataset(path)
        valid_time = gfs_valid_time_for(ds)
        rendered.append(
            str(
                render_anomaly_map(
                    ds["t2m"],
                    step_hours=GFS_STEP_HOURS,
                    valid_time=valid_time,
                    region=region,
                    model="gfs",
                )
            )
        )
    return rendered


def _mark_as_gfs(df: pd.DataFrame) -> pd.DataFrame:
    """to_ts_long()/population_weighted() both hardcode source="open_meteo" in the
    DataFrame they return (see degree_days.py/aggregate.py) -- that's a real column
    value written into the parquet file, not just write_ts_long()'s own partition-path
    parameter, so it must be overridden explicitly here or these rows would be
    misclassified as Open-Meteo's own when read back (core.storage.read_ts_long()
    /pages filter on this column, not on the physical partition directory). Same
    pattern _mark_as_forecast() above already uses for the Open-Meteo forecast rows;
    unlike that one, no series_id suffix is needed here -- GFS has no same-series_id
    historical counterpart of its own to collide with, and write_ts_long's own
    per-source partitioning already keeps every source's rows physically separate
    regardless."""
    df = df.copy()
    df["source"] = "gfs"
    return df


def pull_gfs_degree_days_forecast(ingested_at: pd.Timestamp) -> pd.DataFrame:
    cities_df = load_cities()
    forecast_frames = []
    for base, group_cities in cities_df.groupby("base"):
        daily = sample_gfs_cities(cities_df, str(base))
        forecast_frames.append(to_ts_long(daily, group_cities, ingested_at))

    forecast_long = pd.concat(forecast_frames, ignore_index=True)
    forecast_popw = pd.concat(
        [population_weighted(forecast_long, cities_df, m, ingested_at) for m in ("hdd", "cdd")],
        ignore_index=True,
    )
    return _mark_as_gfs(pd.concat([forecast_long, forecast_popw], ignore_index=True))


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))

    hdd_cdd_forecast = _mark_as_forecast(pull_hdd_cdd_forecast(ingested_at))
    write_ts_long(hdd_cdd_forecast, source="open_meteo_forecast")
    print(f"wrote {len(hdd_cdd_forecast)} HDD/CDD forecast rows", flush=True)

    wind_forecast = _mark_as_forecast(pull_wind_forecast(ingested_at))
    write_ts_long(wind_forecast, source="open_meteo_forecast")
    print(f"wrote {len(wind_forecast)} wind forecast rows", flush=True)

    try:
        rendered = render_daily_anomaly_maps()
        print(f"rendered {len(rendered)} ECMWF anomaly maps: {rendered}", flush=True)
    except Exception as exc:
        # One model's own outage/rate-limit must never block the rest of the daily
        # pull -- same cross-pipeline resilience principle infra/run_scheduled.py
        # already applies one level up, applied here between the two weather models.
        print(f"ECMWF anomaly maps: FAILED ({type(exc).__name__}: {exc})", flush=True)

    try:
        gfs_rendered = render_gfs_anomaly_maps()
        print(f"rendered {len(gfs_rendered)} GFS anomaly maps: {gfs_rendered}", flush=True)
    except Exception as exc:
        print(f"GFS anomaly maps: FAILED ({type(exc).__name__}: {exc})", flush=True)

    try:
        gfs_hdd_cdd = pull_gfs_degree_days_forecast(ingested_at)
        write_ts_long(gfs_hdd_cdd, source="gfs")
        print(f"wrote {len(gfs_hdd_cdd)} GFS HDD/CDD rows", flush=True)
    except Exception as exc:
        print(f"GFS HDD/CDD forecast: FAILED ({type(exc).__name__}: {exc})", flush=True)


if __name__ == "__main__":
    main()
