from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from pipelines.gridstatus_iso.client import GridstatusISOClient
from pipelines.gridstatus_iso.hubs import HUBS

END = date(2026, 8, 25)
START = END - timedelta(days=1)


@pytest.mark.vcr
def test_get_load_returns_hourly_frame() -> None:
    client = GridstatusISOClient("CAISO")
    df = client.get_load(START, END)

    assert not df.empty
    assert set(df.columns) == {"ts", "value"}
    assert df["ts"].dt.tz is None
    # Confirmed live: downsampled to hourly -- consecutive rows one hour apart.
    diffs = df["ts"].diff().dropna().unique()
    assert list(diffs) == [pd.Timedelta(hours=1)]


@pytest.mark.vcr
def test_get_fuel_mix_returns_long_frame() -> None:
    client = GridstatusISOClient("CAISO")
    df = client.get_fuel_mix(START, END)

    assert not df.empty
    assert set(df.columns) == {"ts", "fuel_type", "value"}
    assert "Solar" in df["fuel_type"].unique()


@pytest.mark.vcr
def test_get_lmp_returns_long_frame_by_hub() -> None:
    client = GridstatusISOClient("CAISO")
    df = client.get_lmp(START, END)

    assert not df.empty
    assert set(df.columns) == {"ts", "hub", "value"}
    assert set(df["hub"].unique()) <= set(HUBS["CAISO"])


@pytest.mark.vcr
def test_nyiso_get_load_returns_hourly_frame() -> None:
    client = GridstatusISOClient("NYISO")
    df = client.get_load(START, END)

    assert not df.empty
    assert set(df.columns) == {"ts", "value"}
    assert df["ts"].dt.tz is None
