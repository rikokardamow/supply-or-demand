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


def _synthetic_t2m_2d() -> xr.DataArray:
    """A single-step, 2x2 grid in Kelvin. (lat=50, lon=10) -> 293.15K (20.0C); (lat=53,
    lon=13) -> 292.15K (19.0C) -- the two points a monkeypatched climatology_grid will
    be asked to match exactly (method="nearest" against an exact hit). Matches the
    shape both ecmwf_client.py and gfs_client.py's own load_2t_dataset(...)['t2m']
    reduce to once a caller has already sliced out a single forecast step."""
    data = np.array([[293.15, 300.0], [280.0, 292.15]])
    return xr.DataArray(
        data=data,
        dims=("latitude", "longitude"),
        coords={"latitude": [50.0, 53.0], "longitude": [10.0, 13.0]},
    )


def test_read_manifest_empty_when_no_file_yet() -> None:
    result = anomaly_maps.read_manifest()

    assert result.empty
    assert list(result.columns) == [
        "model",
        "region",
        "step_hours",
        "valid_time",
        "rendered_at",
        "path",
    ]


def test_read_manifest_fills_missing_model_column_as_ecmwf(tmp_path: Path) -> None:
    """A manifest row written before this session (every map rendered so far was
    ECMWF's) has no `model` column at all -- confirm it's filled in rather than
    requiring a manual migration of the existing on-disk file."""
    legacy = pd.DataFrame(
        [
            {
                "region": "eu",
                "step_hours": 72,
                "valid_time": pd.Timestamp("2026-09-04"),
                "rendered_at": pd.Timestamp("2026-09-04"),
                "path": "a.png",
            }
        ]
    )
    anomaly_maps.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    legacy.to_parquet(anomaly_maps.MANIFEST_PATH, index=False)

    result = anomaly_maps.read_manifest()

    assert result.iloc[0]["model"] == "ecmwf"


def test_append_manifest_row_round_trips_and_dedupes() -> None:
    valid_time = pd.Timestamp("2026-09-04T00:00:00")
    anomaly_maps._append_manifest_row("ecmwf", "eu", 72, valid_time, Path("a.png"))
    anomaly_maps._append_manifest_row("ecmwf", "eu", 72, valid_time, Path("b.png"))  # re-render

    result = anomaly_maps.read_manifest()

    assert len(result) == 1  # de-duped on (model, region, step_hours, valid_time)
    assert result.iloc[0]["path"] == "b.png"


def test_append_manifest_row_keeps_distinct_models_separate() -> None:
    """Same region/step_hours/valid_time, different model -- confirmed live this can
    happen (both models can independently publish a "D+3" forecast valid the same
    calendar day) and must never overwrite each other's manifest row."""
    valid_time = pd.Timestamp("2026-09-04T00:00:00")
    anomaly_maps._append_manifest_row("ecmwf", "eu", 72, valid_time, Path("ecmwf.png"))
    anomaly_maps._append_manifest_row("gfs", "eu", 72, valid_time, Path("gfs.png"))

    result = anomaly_maps.read_manifest()

    assert len(result) == 2
    assert set(result["model"]) == {"ecmwf", "gfs"}


def test_render_anomaly_map_writes_png_and_manifest_row(monkeypatch: pytest.MonkeyPatch) -> None:
    clim = pd.DataFrame({"lat": [50.0, 53.0], "lon": [10.0, 13.0], "climatology_c": [15.0, 15.0]})
    monkeypatch.setattr(anomaly_maps, "climatology_grid", lambda region, target_date: clim)

    path = anomaly_maps.render_anomaly_map(
        _synthetic_t2m_2d(),
        step_hours=72,
        valid_time=pd.Timestamp("2026-09-04T00:00:00"),
        region="eu",
        model="gfs",
    )

    assert path.exists()
    assert path.suffix == ".png"
    assert path.name == "anomaly-gfs-eu-d3-20260904.png"

    manifest = anomaly_maps.read_manifest()
    assert len(manifest) == 1
    row = manifest.iloc[0]
    assert row["model"] == "gfs"
    assert row["region"] == "eu"
    assert row["step_hours"] == 72
    assert pd.Timestamp(row["valid_time"]) == pd.Timestamp("2026-09-04T00:00:00")
    assert row["path"] == str(path)
