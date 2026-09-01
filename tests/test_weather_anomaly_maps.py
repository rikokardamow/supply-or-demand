from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from pipelines.weather import anomaly_maps


@pytest.fixture(autouse=True)
def _isolated_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    maps_dir = tmp_path / "maps"
    monkeypatch.setattr(anomaly_maps, "MAPS_DIR", maps_dir)
    monkeypatch.setattr(anomaly_maps, "MANIFEST_PATH", maps_dir / "manifest.parquet")


def _synthetic_t2m() -> xr.DataArray:
    """A 1-step, 2x2 grid in Kelvin. (lat=50, lon=10) -> 293.15K (20.0C); (lat=53,
    lon=13) -> 292.15K (19.0C) -- the two points a monkeypatched climatology_grid will
    be asked to match exactly (method="nearest" against an exact hit)."""
    data = np.array([[[293.15, 300.0], [280.0, 292.15]]])
    return xr.DataArray(
        data=data,
        dims=("step", "latitude", "longitude"),
        coords={
            "step": [pd.Timedelta(hours=72)],
            "latitude": [50.0, 53.0],
            "longitude": [10.0, 13.0],
            "valid_time": ("step", [pd.Timestamp("2026-09-04T00:00:00")]),
        },
    )


def test_read_manifest_empty_when_no_file_yet() -> None:
    result = anomaly_maps.read_manifest()

    assert result.empty
    assert list(result.columns) == ["region", "step_hours", "valid_time", "rendered_at", "path"]


def test_append_manifest_row_round_trips_and_dedupes() -> None:
    valid_time = pd.Timestamp("2026-09-04T00:00:00")
    anomaly_maps._append_manifest_row("eu", 72, valid_time, Path("a.png"))
    anomaly_maps._append_manifest_row("eu", 72, valid_time, Path("b.png"))  # re-render, same key

    result = anomaly_maps.read_manifest()

    assert len(result) == 1  # de-duped on (region, step_hours, valid_time), keep last
    assert result.iloc[0]["path"] == "b.png"


def test_render_anomaly_map_writes_png_and_manifest_row(monkeypatch: pytest.MonkeyPatch) -> None:
    clim = pd.DataFrame(
        {"lat": [50.0, 53.0], "lon": [10.0, 13.0], "climatology_c": [15.0, 15.0]}
    )
    monkeypatch.setattr(anomaly_maps, "climatology_grid", lambda region, target_date: clim)

    path = anomaly_maps.render_anomaly_map(_synthetic_t2m(), step_index=0, region="eu")

    assert path.exists()
    assert path.suffix == ".png"
    assert path.name == "anomaly-eu-d3-20260904.png"

    manifest = anomaly_maps.read_manifest()
    assert len(manifest) == 1
    row = manifest.iloc[0]
    assert row["region"] == "eu"
    assert row["step_hours"] == 72
    assert pd.Timestamp(row["valid_time"]) == pd.Timestamp("2026-09-04T00:00:00")
    assert row["path"] == str(path)
