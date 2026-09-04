"""Renders 2m-temperature anomaly maps (model forecast minus the recent-normal grid from
climatology_grid.py) for EU and CONUS at D+3/D+7, "tropicaltidbits-style": cartopy
coastlines/borders, diverging blue-white-red colour scale centred on zero anomaly.
Model-agnostic (ECMWF IFS and, since the weather-module-spec.md Phase 1 session, GFS) --
`render_anomaly_map` takes an already-single-step 2D DataArray plus that step's own
valid_time, so each model's own client/pull script handles its own step-extraction
quirks (ECMWF's fetch is one multi-step file; GFS's is one file per step -- see
gfs_client.py's own docstring) rather than this shared rendering function needing to
know about either.

Cartopy confirmed live to install and render cleanly via pip on Windows (no system
GEOS/PROJ needed -- modern wheels bundle them) -- no matplotlib-only fallback needed.

Maps are written as PNG files under data/lake/maps/, with one manifest row per map in
data/lake/maps/manifest.parquet -- a plain Parquet file, not a real persisted DuckDB
table file, even though the spec's own Data Model section names "DuckDB table
map_assets". No precedent for a persisted (non-in-memory) DuckDB file exists anywhere
else in this project (core.storage.warehouse() only ever registers views over Parquet
globs) -- introducing one for a single small metadata table felt like a bigger
architectural step than this session should take unilaterally. A manifest row is a
manifest row either way; this can be swapped for a real DuckDB file later without
changing any caller if that's ever wanted."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
from cartopy.mpl.geoaxes import GeoAxes

matplotlib.use("Agg")  # headless rendering -- this runs inside a pipeline, not a GUI
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

from pipelines.weather.climatology_grid import REGION_BOUNDS, climatology_grid

MAPS_DIR = Path("data/lake/maps")
MANIFEST_PATH = MAPS_DIR / "manifest.parquet"
ANOMALY_VMIN_VMAX = 8.0  # degrees C either side of zero -- fixed scale for comparability


def _region_extent(region: str) -> tuple[float, float, float, float]:
    bounds = REGION_BOUNDS[region]
    lat_min, lat_max = bounds["lat"]
    lon_min, lon_max = bounds["lon"]
    return (lon_min, lon_max, lat_min, lat_max)


def render_anomaly_map(
    t2m_2d: xr.DataArray,
    step_hours: int,
    valid_time: pd.Timestamp,
    region: str,
    model: str = "ecmwf",
) -> Path:
    """`t2m_2d` is a single forecast step's (latitude, longitude) DataArray in Kelvin,
    longitude already normalised to -180..180 -- both ecmwf_client.load_2t_dataset and
    gfs_client.load_2t_dataset already guarantee this. `step_hours`/`valid_time` are
    passed explicitly rather than read off `t2m_2d` itself, since ECMWF's own step
    coordinate survives an `.isel(step=...)` slice but GFS's per-step files don't carry
    one in the same shape -- see each model's own pull script for how it extracts these."""
    clim = climatology_grid(region, valid_time.date())
    lats = xr.DataArray(clim["lat"].to_numpy(), dims="points")
    lons = xr.DataArray(clim["lon"].to_numpy(), dims="points")
    forecast_c = (
        t2m_2d.sel(latitude=lats, longitude=lons, method="nearest").to_numpy() - 273.15
    )
    anomaly = forecast_c - clim["climatology_c"].to_numpy()

    fig = plt.figure(figsize=(8, 6))
    ax: GeoAxes = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent(_region_extent(region))
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6)
    ax.add_feature(cfeature.BORDERS, linewidth=0.4, linestyle=":")

    scatter = ax.scatter(
        clim["lon"],
        clim["lat"],
        c=anomaly,
        cmap="RdBu_r",
        vmin=-ANOMALY_VMIN_VMAX,
        vmax=ANOMALY_VMIN_VMAX,
        s=60,
        marker="s",
        transform=ccrs.PlateCarree(),
    )
    fig.colorbar(scatter, ax=ax, label="2m-temp anomaly (°C)", shrink=0.8)
    ax.set_title(
        f"{region.upper()} 2m-Temp Anomaly ({model.upper()}) — D+{step_hours // 24} "
        f"({valid_time:%Y-%m-%d}) vs {climatology_years_label()}",
        fontsize=9,
    )

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"anomaly-{model}-{region}-d{step_hours // 24}-{valid_time:%Y%m%d}.png"
    path = MAPS_DIR / filename
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)

    _append_manifest_row(model, region, step_hours, valid_time, path)
    return path


def climatology_years_label() -> str:
    from pipelines.weather.climatology_grid import CLIMATOLOGY_YEARS

    return "/".join(str(y) for y in CLIMATOLOGY_YEARS) + " normal"


def _append_manifest_row(
    model: str, region: str, step_hours: int, valid_time: pd.Timestamp, path: Path
) -> None:
    row = pd.DataFrame(
        [
            {
                "model": model,
                "region": region,
                "step_hours": step_hours,
                "valid_time": valid_time,
                "rendered_at": pd.Timestamp(datetime.now(UTC)),
                "path": str(path),
            }
        ]
    )
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST_PATH.exists():
        existing = read_manifest()
        combined = pd.concat([existing, row], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["model", "region", "step_hours", "valid_time"], keep="last"
        )
    else:
        combined = row
    combined.to_parquet(MANIFEST_PATH, index=False)


def read_manifest() -> pd.DataFrame:
    """A manifest row written before this session has no `model` column at all (every
    map rendered so far was ECMWF's) -- filled in as "ecmwf" here rather than requiring
    a one-off migration script, so the existing on-disk file needs no manual backfill."""
    if not MANIFEST_PATH.exists():
        return pd.DataFrame(
            columns=["model", "region", "step_hours", "valid_time", "rendered_at", "path"]
        )
    manifest = pd.read_parquet(MANIFEST_PATH)
    if "model" not in manifest.columns:
        manifest["model"] = "ecmwf"
    return manifest
