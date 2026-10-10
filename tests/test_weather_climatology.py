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


class _ReadTsLongSpy:
    """Stands in for `core.storage.read_ts_long`. Records the kwargs it was called
    with (so a test can pin that `build_climatology` requests `source="open_meteo"`)
    and narrows the synthetic frame the same way the real, source-partitioned
    `read_ts_long` would -- so a test using this spy exercises the same post-narrowing
    frame `build_climatology` would see for real, not the whole unfiltered lake."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        series_ids: list[str] | None = None,
        start: object = None,
        end: object = None,
        source: str | None = None,
        series_prefix: str | None = None,
    ) -> pd.DataFrame:
        self.calls.append(
            {
                "series_ids": series_ids,
                "source": source,
                "series_prefix": series_prefix,
            }
        )
        result = self._df
        if source is not None:
            result = result[result["source"] == source]
        if series_prefix is not None:
            result = result[result["series_id"].str.startswith(series_prefix)]
        return result


def test_build_climatology_excludes_2020(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(climatology_module, "read_ts_long", _ReadTsLongSpy(_synthetic_long_df()))
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
    spy = _ReadTsLongSpy(_synthetic_long_df())
    monkeypatch.setattr(climatology_module, "read_ts_long", spy)
    monkeypatch.setattr(climatology_module, "CLIMATOLOGY_YEARS", range(2018, 2022))
    cache_path = tmp_path / "climatology.parquet"

    climatology_module.build_climatology(cache_path=cache_path)
    climatology_module.build_climatology(cache_path=cache_path)

    assert len(spy.calls) == 1


def test_build_climatology_narrows_read_to_open_meteo_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build_climatology` must ask `read_ts_long` for `source="open_meteo"` rather
    than materialising the whole lake and filtering source in pandas afterward (the
    17x over-read this module's docstring already claimed was fixed but wasn't). The
    spy narrows the synthetic frame exactly as the real source-partitioned read would,
    so this also proves the narrowing doesn't change build_climatology's own output
    (still just hdd.dublin.c18, still median 8.0, 2020 still excluded)."""
    spy = _ReadTsLongSpy(_synthetic_long_df())
    monkeypatch.setattr(climatology_module, "read_ts_long", spy)
    monkeypatch.setattr(climatology_module, "CLIMATOLOGY_YEARS", range(2018, 2022))
    cache_path = tmp_path / "climatology.parquet"

    result = climatology_module.build_climatology(cache_path=cache_path)

    assert spy.calls, "read_ts_long was never called"
    assert spy.calls[0]["source"] == "open_meteo"
    assert set(result["series_id"]) == {"hdd.dublin.c18"}
    assert (result["climatology"] == 8.0).all()
