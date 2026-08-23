from __future__ import annotations

import pytest
from pipelines.eia.client import EIAClient

EXPECTED_COLUMNS = {
    "series_id",
    "source",
    "ts",
    "value",
    "unit",
    "geo",
    "freq",
    "revision_date",
}


@pytest.mark.vcr
def test_get_series_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/stoc/wstk", series=["WCESTUS1"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS
    assert (df["series_id"] == "WCESTUS1").all()
    assert (df["source"] == "eia").all()
    assert df["value"].dtype.kind == "f"
