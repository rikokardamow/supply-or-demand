"""NOAA/NCEP GFS client -- 2m-temperature forecast via NOMADS' GRIB-filter service.
Free, public domain, no key. Confirmed live (2026-09-04): the filter endpoint downloads
one small, already-subset GRIB2 per (region, forecast step) -- unlike ecmwf_client.py's
single multi-step global file, GFS needs one HTTP request per distinct forecast hour
(NOMADS' own `file=gfs.t{HH}z.pgrb2.0p25.f{FFF}` naming is per-step, not a step list) and
per bounding box (`leftlon`/`rightlon`/`toplat`/`bottomlat` are server-side subregion
params, not a client-side crop).

Two real gotchas confirmed live, not assumed:
1. **Longitude convention is inconsistent, not just "0..360 always"**: a CONUS bbox
   (leftlon=-125, rightlon=-65 -- entirely west of Greenwich, no wraparound in the
   native 0..360 grid) comes back with longitude in 0..360 (235..295). A EU bbox
   (leftlon=-10, rightlon=30 -- straddles the Greenwich meridian) comes back already in
   -180..180 (-10..30), matching the request directly. `load_2t_dataset` normalizes
   every dataset's longitude to -180..180 unconditionally so downstream code (the same
   REGION_BOUNDS/climatology_grid.py used for ECMWF) never needs to special-case GFS.
2. **A not-yet-published cycle returns HTTP 403 with an HTML "Request for future data"
   body, not a 404.** `fetch_2t_forecast` tries the computed latest-expected cycle first
   and falls back exactly one cycle earlier (6h) on a 403 -- capped at one retry, since a
   second consecutive 403 means something is genuinely wrong (NOMADS outage, wrong date),
   not just "still processing"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import xarray as xr

from pipelines.weather.climatology_grid import REGION_BOUNDS

CACHE_DIR = Path("data/raw/gfs")
FILTER_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
FORECAST_STEP_HOURS = 72  # D+3 only for Phase 1 -- matches this pipeline's own
# session-sized-scope precedent (D+7 is a natural follow-on once this is proven).

# GFS cycles publish roughly 3.5-4h after their own init hour (confirmed live: at
# 08:15 UTC on 2026-09-04, the 00z cycle was already available). A conservative 4.5h
# buffer picks the most recent cycle that should realistically be ready.
PUBLICATION_LAG_HOURS = 4.5
CYCLE_HOURS = (0, 6, 12, 18)


def _latest_expected_cycle(now: datetime) -> datetime:
    """Returns the most recent GFS cycle (as a UTC datetime at hour 0/6/12/18) that
    should already be published, given PUBLICATION_LAG_HOURS."""
    candidate = now - timedelta(hours=PUBLICATION_LAG_HOURS)
    cycle_hour = max(h for h in CYCLE_HOURS if h <= candidate.hour)
    return candidate.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)


def _previous_cycle(run: datetime) -> datetime:
    idx = CYCLE_HOURS.index(run.hour)
    if idx == 0:
        return (run - timedelta(days=1)).replace(hour=CYCLE_HOURS[-1])
    return run.replace(hour=CYCLE_HOURS[idx - 1])


def _build_url(run: datetime, step_hours: int, region: str) -> str:
    bounds = REGION_BOUNDS[region]
    lat_min, lat_max = bounds["lat"]
    lon_min, lon_max = bounds["lon"]
    hh = f"{run.hour:02d}"
    return (
        f"{FILTER_URL}?file=gfs.t{hh}z.pgrb2.0p25.f{step_hours:03d}"
        "&lev_2_m_above_ground=on&var_TMP=on&subregion="
        f"&leftlon={lon_min}&rightlon={lon_max}&toplat={lat_max}&bottomlat={lat_min}"
        f"&dir=%2Fgfs.{run:%Y%m%d}%2F{hh}%2Fatmos"
    )


def _cache_path(run: datetime, step_hours: int, region: str) -> Path:
    return CACHE_DIR / f"gfs-2t-{region}-{run:%Y%m%dT%H}-f{step_hours:03d}.grib2"


def fetch_2t_forecast(
    region: str, step_hours: int = FORECAST_STEP_HOURS, now: datetime | None = None
) -> tuple[Path, datetime]:
    """Downloads (or reuses a cached) GFS 2t GRIB2 subset for `region` at `step_hours`
    lead time. Returns (path, run_datetime) -- the run_datetime is needed by callers for
    the same "model, init time, valid time" captioning ecmwf_client.py's own run
    datetime already provides. Tries the latest expected cycle, falls back one cycle
    (6h) earlier on an HTTP 403 (NOMADS' real "not yet published" signal, confirmed
    live -- not a 404)."""
    if now is None:
        now = datetime.now(UTC)
    run = _latest_expected_cycle(now)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for attempt_run in (run, _previous_cycle(run)):
        cache_path = _cache_path(attempt_run, step_hours, region)
        if cache_path.exists():
            return cache_path, attempt_run

        response = requests.get(_build_url(attempt_run, step_hours, region), timeout=60)
        if response.status_code == 403:
            continue  # not yet published -- fall back to the previous cycle
        response.raise_for_status()
        cache_path.write_bytes(response.content)
        return cache_path, attempt_run

    raise RuntimeError(
        f"GFS {region} f{step_hours:03d}: no published cycle found at or before "
        f"{run:%Y-%m-%d %HZ} (tried this cycle and the one before)"
    )


def load_2t_dataset(path: Path) -> xr.Dataset:
    """Opens a cached GFS 2t GRIB2 as an xarray Dataset (via cfgrib) and normalises
    longitude to -180..180 -- see this module's own docstring for why the raw
    convention isn't consistent across regions."""
    ds = xr.open_dataset(path, engine="cfgrib")
    normalised_lon = ((ds["longitude"] + 180) % 360) - 180
    ds = ds.assign_coords(longitude=normalised_lon).sortby("longitude")
    return ds


def valid_time_for(ds: xr.Dataset) -> pd.Timestamp:
    return pd.Timestamp(ds["valid_time"].values.item())
