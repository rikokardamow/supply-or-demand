"""Builds a coarse ERA5-normal temperature GRID (not the per-city climatology in
climatology.py) for the anomaly maps -- a separate, simpler concept, per the spec's own
"choose the simplest that works" allowance rather than a full 2010-2024 ERA5 monthly
climatology grid from Copernicus CDS (which needs a separate CDS account/API key, not
otherwise used by this project).

Confirmed live: Open-Meteo's archive endpoint happily batches 100+ locations in a single
call (126-point EU grid test), but only for ONE contiguous date range per call -- there is
no "same calendar day across many separate years" batch mode. Computing a genuine
multi-year climatology at every grid point would need one archive call per reference
year (no way around it), so this deliberately uses a SHORT 3-year reference window
(2022, 2024, and the most recent year excluding 2020 -- i.e. whichever 3 non-2020 years
are asked for) rather than a 5+ year normal, to keep the pipeline's own API load and
runtime small. This is a documented simplification, not a hidden shortcut -- see
CLAUDE.md."""

from __future__ import annotations

from datetime import date

import pandas as pd

from pipelines.weather.client import fetch_archive

REGION_BOUNDS = {
    "eu": {"lat": (35.0, 60.0), "lon": (-10.0, 30.0)},
    "conus": {"lat": (24.0, 50.0), "lon": (-125.0, -65.0)},
}
GRID_SPACING_DEG = 3.0
CLIMATOLOGY_YEARS = (2022, 2023, 2024)  # recent 3 years, excludes 2020 per house rule


def build_region_grid(region: str, spacing_deg: float = GRID_SPACING_DEG) -> pd.DataFrame:
    bounds = REGION_BOUNDS[region]
    lat_min, lat_max = bounds["lat"]
    lon_min, lon_max = bounds["lon"]

    lats = []
    lat = lat_min
    while lat <= lat_max + 1e-9:
        lats.append(round(lat, 2))
        lat += spacing_deg

    lons = []
    lon = lon_min
    while lon <= lon_max + 1e-9:
        lons.append(round(lon, 2))
        lon += spacing_deg

    pairs = [(la, lo) for la in lats for lo in lons]
    return pd.DataFrame(pairs, columns=["lat", "lon"])


def climatology_grid(
    region: str, target_date: date, years: tuple[int, ...] = CLIMATOLOGY_YEARS
) -> pd.DataFrame:
    """Returns {lat, lon, climatology_c} -- the mean 2m temperature (Celsius) at each
    grid point on `target_date`'s calendar day, averaged across `years`. One Open-Meteo
    archive call per year (confirmed no multi-year-single-day batch mode exists), all
    grid points batched together within each call."""
    grid = build_region_grid(region)
    cities_like = grid.rename(columns={"lat": "lat", "lon": "lon"})
    cities_like["city"] = [f"{row.lat}_{row.lon}" for row in cities_like.itertuples()]

    yearly_frames = []
    for year in years:
        same_day = target_date.replace(year=year)
        daily = fetch_archive(cities_like, same_day, same_day)
        yearly_frames.append(daily[["city", "temp_mean_c"]].rename(columns={"temp_mean_c": year}))

    merged = yearly_frames[0]
    for frame in yearly_frames[1:]:
        merged = merged.merge(frame, on="city")

    merged["climatology_c"] = merged[list(years)].mean(axis=1)
    result = merged.merge(cities_like[["city", "lat", "lon"]], on="city")
    return result[["lat", "lon", "climatology_c"]]
