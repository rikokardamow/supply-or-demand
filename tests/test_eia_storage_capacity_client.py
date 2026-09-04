from __future__ import annotations

import pandas as pd
import pytest
from pipelines.eia_storage_capacity.client import fetch_cushing_capacity


@pytest.mark.vcr
def test_fetch_cushing_capacity_real_last_report_row() -> None:
    """crudeoilstorage.xlsx is a small, real, non-secret public government file -- safe
    to commit as a vcrpy cassette, matching this project's dominant testing convention
    (e.g. tests/test_weather_gfs_client.py's own real, binary GRIB2 cassette)."""
    df = fetch_cushing_capacity()

    assert not df.empty
    assert list(df.columns) == ["ts", "value"]

    last = df.iloc[-1]
    assert last["ts"] == pd.Timestamp("2024-03-01")
    assert last["value"] == pytest.approx(80604.0)


@pytest.mark.vcr
def test_fetch_cushing_capacity_covers_the_confirmed_real_date_range() -> None:
    df = fetch_cushing_capacity()
    assert df["ts"].min() == pd.Timestamp("2011-03-31")
    assert df["ts"].max() == pd.Timestamp("2024-03-01")
    assert len(df) == 23
