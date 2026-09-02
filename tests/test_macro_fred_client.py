from __future__ import annotations

import pandas as pd
import pytest
from pipelines.macro.fred_client import FREDClient


@pytest.mark.vcr
def test_get_series_returns_real_index_series() -> None:
    df = FREDClient().get_series("CPIAUCSL")

    assert list(df.columns) == ["ts", "value"]
    assert not df.empty
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    assert pd.api.types.is_numeric_dtype(df["value"])


@pytest.mark.vcr
def test_get_series_returns_real_daily_energy_series() -> None:
    df = FREDClient().get_series("DCOILWTICO")

    assert not df.empty
    # Not "every value > 0" -- WTI's real full history includes the famous
    # 2020-04-20 negative print (-$36.98, confirmed live), so only the latest value
    # is checked for a plausible positive price.
    assert df["value"].iloc[-1] > 0
