"""ECMWF Open Data client -- IFS HRES 2m-temperature forecast, steps D+3/D+7 (72h/168h).
Free, fully open (CC-BY-4.0) since 1 Oct 2025, no key. Confirmed live: `Client(source=
"ecmwf")`'s default model="ifs"/resol="0p25" returns a real forecast (a ~1.25MB GRIB2 for
2 steps x global 2t), attribution required by ECMWF's own terms message on every
download -- see NOTES.md for the exact attribution line to carry on the page."""

from __future__ import annotations

from pathlib import Path

import xarray as xr
from ecmwf.opendata import Client

CACHE_DIR = Path("data/raw/ecmwf")
FORECAST_STEPS = (72, 168)  # D+3, D+7 -- confirmed live these are valid IFS steps


def fetch_2t_forecast(steps: tuple[int, ...] = FORECAST_STEPS) -> Path:
    """Downloads (or reuses a cached) IFS 2t GRIB2 for the given forecast steps.
    Cached by the real forecast run datetime (not "today") -- `Client.latest()`
    (confirmed live) returns just the current run's datetime without downloading the
    actual field, so a cache hit costs one small metadata request, not a full
    re-download."""
    client = Client(source="ecmwf")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    request = {"type": "fc", "step": list(steps), "param": ["2t"]}
    run_datetime = client.latest(**request)
    run_stamp = run_datetime.strftime("%Y%m%dT%H%M")
    cache_path = CACHE_DIR / f"ifs-2t-{run_stamp}.grib2"

    if not cache_path.exists():
        client.retrieve(**request, target=str(cache_path))

    return cache_path


def load_2t_dataset(path: Path) -> xr.Dataset:
    """Opens a cached IFS 2t GRIB2 as an xarray Dataset (via cfgrib). Confirmed live:
    variable name `t2m`, units Kelvin, dims (step, latitude, longitude), latitude
    90..-90, longitude already in -180..180 (not 0..360) -- no wraparound conversion
    needed to match EU/CONUS bounding boxes."""
    return xr.open_dataset(path, engine="cfgrib")
