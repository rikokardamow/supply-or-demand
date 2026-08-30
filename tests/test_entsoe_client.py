from __future__ import annotations

from datetime import date

import pytest
from pipelines.entsoe.client import ENTSOEClient


@pytest.mark.vcr
def test_get_day_ahead_prices_returns_raw_frame() -> None:
    client = ENTSOEClient()
    df = client.get_day_ahead_prices("DE_LU", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    assert set(df.columns) == {"ts", "value", "freq"}
    assert df["value"].dtype.kind == "f"
    # Real DE_LU day-ahead prices are plausible tens-to-low-hundreds EUR/MWh, not e.g.
    # accidentally left in some other unit or scale.
    assert 0 < df["value"].abs().median() < 1000
    # Confirmed live during planning: DE_LU is 15-minute resolution, not hourly.
    assert (df["freq"] == "15T").all()
    # ts must be tz-naive (entsoe-py returns a tz-aware, zone-local index — converted
    # to naive UTC before this point).
    assert df["ts"].dt.tz is None
