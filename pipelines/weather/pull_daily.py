"""Session C's daily incremental entrypoint (Spec 13 orchestration), distinct from
pull_weather.py's one-off multi-year history backfill: refreshes the 16-day Open-Meteo
forecast (HDD/CDD for the 14 cities + pop-weighted aggregates, plus the DE/DK/IE wind
index) and re-renders the 4 ECMWF anomaly maps. write_ts_long's own (series_id, ts)
de-dup (keep latest revision_date) makes a daily re-pull of an overlapping forecast
window naturally idempotent, same reasoning as pipelines/entsoe/pull_daily.py's prices/
load/generation re-pulls needing no extra revision-window logic."""

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
            rendered.append(str(render_anomaly_map(t2m, step_index=step_index, region=region)))
    return rendered


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))

    hdd_cdd_forecast = _mark_as_forecast(pull_hdd_cdd_forecast(ingested_at))
    write_ts_long(hdd_cdd_forecast, source="open_meteo_forecast")
    print(f"wrote {len(hdd_cdd_forecast)} HDD/CDD forecast rows", flush=True)

    wind_forecast = _mark_as_forecast(pull_wind_forecast(ingested_at))
    write_ts_long(wind_forecast, source="open_meteo_forecast")
    print(f"wrote {len(wind_forecast)} wind forecast rows", flush=True)

    rendered = render_daily_anomaly_maps()
    print(f"rendered {len(rendered)} anomaly maps: {rendered}", flush=True)


if __name__ == "__main__":
    main()
