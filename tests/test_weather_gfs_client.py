from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pipelines.weather import gfs_client

# Fixed "now" matching exactly what was used to record the real cassette this test
# replays against -- vcrpy matches on the full request URI (method/file/dir/bbox
# params), which is built from `now` via _latest_expected_cycle(), so a different
# `now` on replay would construct a different URL and fail to match the cassette.
_RECORDED_NOW = datetime(2026, 9, 4, 8, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gfs_client, "CACHE_DIR", tmp_path)


def test_latest_expected_cycle_picks_the_most_recent_published_cycle() -> None:
    # 08:15 UTC, 4.5h publication lag -> candidate hour 3 -> most recent cycle <= 3 is 00z.
    result = gfs_client._latest_expected_cycle(_RECORDED_NOW)

    assert result == datetime(2026, 9, 4, 0, 0, tzinfo=UTC)


def test_previous_cycle_steps_back_within_the_same_day() -> None:
    run = datetime(2026, 9, 4, 12)
    assert gfs_client._previous_cycle(run) == datetime(2026, 9, 4, 6)


def test_previous_cycle_steps_back_across_midnight() -> None:
    run = datetime(2026, 9, 4, 0)
    assert gfs_client._previous_cycle(run) == datetime(2026, 9, 3, 18)


@pytest.mark.vcr
def test_fetch_2t_forecast_downloads_a_real_eu_subset_and_caches() -> None:
    path1, run1 = gfs_client.fetch_2t_forecast("eu", now=_RECORDED_NOW)
    path2, run2 = gfs_client.fetch_2t_forecast("eu", now=_RECORDED_NOW)

    assert path1 == path2  # second call is a cache hit, no new cassette interaction needed
    assert run1 == run2
    assert path1.exists()
    assert path1.read_bytes().startswith(b"GRIB")


@pytest.mark.vcr
def test_load_2t_dataset_normalises_longitude_and_parses_real_t2m() -> None:
    path, _run = gfs_client.fetch_2t_forecast("conus", now=_RECORDED_NOW)

    ds = gfs_client.load_2t_dataset(path)

    # Confirmed live: CONUS's raw response comes back in 0..360 convention (235..295);
    # normalisation must always land in -180..180 regardless of the raw convention.
    assert float(ds["longitude"].min()) >= -180.0
    assert float(ds["longitude"].max()) <= -60.0
    assert "t2m" in ds
    valid_time = gfs_client.valid_time_for(ds)
    assert valid_time.year == 2026
