"""Forecast 10m-wind cross-check for DE/DK/IE (specs/08_weather.md's visualisation item
4) -- reuses client.py's own daily wind_speed_10m_max output (already parsed as
wind_max_kmh, no new API call shape needed), for one representative point per country
(pipelines/weather/wind_locations.csv -- Berlin, Copenhagen, Dublin; Dublin's coordinates
match cities.csv exactly, kept as a separate small CSV since population_weight/HDD base
don't apply here).

Compared on page 08 against ENTSO-E's own wind generation forecast for the matching
bidding zone (pipelines/entsoe: entsoe.{zone}.forecast.wind_onshore/wind_offshore) as an
independent-source timing cross-check, not a unit conversion -- the two series share no
common unit (km/h vs MW), so the chart is a dual-axis "does the shape agree" check, same
pattern as this page's existing HDD-anomaly-vs-gas-withdrawal charts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

WIND_LOCATIONS_CSV_PATH = Path(__file__).parent / "wind_locations.csv"


def load_wind_locations(path: Path = WIND_LOCATIONS_CSV_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def wind_forecast_to_ts_long(
    daily_df: pd.DataFrame, locations_df: pd.DataFrame, revision_date: pd.Timestamp
) -> pd.DataFrame:
    """`daily_df` needs columns city, ts, wind_max_kmh (client.py's own output shape).
    Returns ts_long rows: series_id `wind.{country}.10m_max_kmh` (lowercased),
    geo=country -- the spec asks for a DE/DK/IE cross-check against a whole ENTSO-E
    bidding zone, not one town's reading, so geo is the country, not the city -- unit
    "km/h", freq "D"."""
    merged = daily_df.merge(locations_df[["city", "country"]], on="city", how="left")
    if merged["country"].isna().any():
        missing = sorted(merged.loc[merged["country"].isna(), "city"].unique())
        raise ValueError(f"No country found in locations_df for: {missing}")

    return pd.DataFrame(
        {
            "series_id": "wind." + merged["country"].str.lower() + ".10m_max_kmh",
            "source": "open_meteo",
            "ts": merged["ts"],
            "value": merged["wind_max_kmh"],
            "unit": "km/h",
            "geo": merged["country"],
            "freq": "D",
            "revision_date": revision_date,
        }
    )
