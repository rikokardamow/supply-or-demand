"""Samples the GFS 2m-temperature forecast at the same 14 cities.csv locations the
Open-Meteo path already uses, then reuses degree_days.to_ts_long()/aggregate.
population_weighted() unchanged -- output series_id (hdd.<city>.<base>, hdd.eu.popw,
hdd.us.popw, etc.) are identical to the Open-Meteo path's own, distinguished only by
`source="gfs"` (parallel to the existing "open_meteo"/"open_meteo_forecast" rows for
the same series_id -- the established multi-source-per-series_id pattern this lake
already uses everywhere else, e.g. pipelines/eia's several sources sharing source="eia").

Phase 1 scope, confirmed with the user: the *same* two aggregates the Open-Meteo path
computes (EU-9-city, US-5-city) -- no census-division/EIA-gas-region/ERCOT breakdown,
no new region polygons. That's explicitly a later phase."""

from __future__ import annotations

import pandas as pd
import xarray as xr

from pipelines.weather.gfs_client import fetch_2t_forecast, load_2t_dataset, valid_time_for

# cities.csv's own "base" values map to a region for population_weighted()'s own
# _REGION_BY_BASE ("eu"/"us"); gfs_client/climatology_grid's REGION_BOUNDS instead key
# on "eu"/"conus" -- a bare naming difference between the two pipelines' own
# pre-existing region labels, not a new concept.
_GFS_REGION_BY_BASE = {"c18": "eu", "f65": "conus"}


def sample_cities(cities_df: pd.DataFrame, base: str) -> pd.DataFrame:
    """Returns a daily_df (city, ts, temp_mean_c) in degree_days.to_ts_long()'s own
    expected shape, sampled (nearest-neighbour, same technique anomaly_maps.py already
    uses) from a single GFS forecast step for every city in `cities_df` with this
    `base`."""
    region = _GFS_REGION_BY_BASE[base]
    path, _run = fetch_2t_forecast(region)
    ds = load_2t_dataset(path)
    valid_time = valid_time_for(ds)

    group = cities_df[cities_df["base"] == base]
    lats = xr.DataArray(group["lat"].to_numpy(), dims="points")
    lons = xr.DataArray(group["lon"].to_numpy(), dims="points")
    temp_k = ds["t2m"].sel(latitude=lats, longitude=lons, method="nearest").to_numpy()

    return pd.DataFrame(
        {
            "city": group["city"].to_numpy(),
            "ts": valid_time,
            "temp_mean_c": temp_k - 273.15,
        }
    )
