from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pipelines.weather import climatology as climatology_module


def _synthetic_long_df() -> pd.DataFrame:
    """2018-2021 daily hdd.dublin.c18 = 8 every year except 2020, an extreme outlier
    (18.0) -- if 2020 weren't excluded from the climatology median, this day-of-year's
    figure would shift; the test confirms it doesn't. Includes a non-hdd/cdd series and
    a "open_meteo_forecast"-sourced row to confirm both are filtered out."""
    dates = pd.date_range("2018-01-01", "2021-12-31", freq="D")
    dates = dates[~((dates.month == 2) & (dates.day == 29))]
    values = [18.0 if d.year == 2020 else 8.0 for d in dates]

    rows = pd.DataFrame(
        {
            "series_id": "hdd.dublin.c18",
            "source": "open_meteo",
            "ts": dates,
            "value": values,
            "unit": "degree-days",
            "geo": "dublin",
            "freq": "D",
            "revision_date": pd.Timestamp("2026-08-31"),
        }
    )
    other_source = rows.iloc[[0]].copy()
    other_source["source"] = "open_meteo_forecast"
    other_source["series_id"] = "hdd.dublin.c18.forecast"
    unrelated_series = rows.iloc[[0]].copy()
    unrelated_series["series_id"] = "agsi.EU.injection"

    return pd.concat([rows, other_source, unrelated_series], ignore_index=True)


def test_build_climatology_excludes_2020(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        climatology_module, "read_ts_long", lambda series_ids=None: _synthetic_long_df()
    )
    monkeypatch.setattr(climatology_module, "CLIMATOLOGY_YEARS", range(2018, 2022))
    cache_path = tmp_path / "climatology.parquet"

    result = climatology_module.build_climatology(cache_path=cache_path)

    assert cache_path.exists()
    assert set(result["series_id"]) == {"hdd.dublin.c18"}  # non-hdd/cdd & forecast rows dropped
    # value=8 every non-2020 year -> median must be 8, not skewed toward 2020's 18 if
    # it were wrongly included.
    assert (result["climatology"] == 8.0).all()


def test_build_climatology_reuses_a_fresh_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def _counting_read(series_ids: list[str] | None = None) -> pd.DataFrame:
        nonlocal call_count
        call_count += 1
        return _synthetic_long_df()

    monkeypatch.setattr(climatology_module, "read_ts_long", _counting_read)
    monkeypatch.setattr(climatology_module, "CLIMATOLOGY_YEARS", range(2018, 2022))
    cache_path = tmp_path / "climatology.parquet"

    climatology_module.build_climatology(cache_path=cache_path)
    climatology_module.build_climatology(cache_path=cache_path)

    assert call_count == 1
