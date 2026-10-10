from __future__ import annotations

from datetime import date

import pytest
from pipelines.cftc.client import CFTCClient


@pytest.mark.vcr
def test_get_disaggregated_returns_real_columns_and_dtypes() -> None:
    client = CFTCClient()
    df = client.get_disaggregated("cl", start=date(2026, 8, 1), end=date(2026, 8, 31))

    assert not df.empty
    assert list(df.columns) == [
        "date",
        "root",
        "mm_long",
        "mm_short",
        "prod_merc_long",
        "prod_merc_short",
        "oi",
    ]
    assert (df["root"] == "cl").all()
    for col in ("mm_long", "mm_short", "prod_merc_long", "prod_merc_short", "oi"):
        assert df[col].dtype.kind == "f"


@pytest.mark.vcr
def test_get_disaggregated_rejects_unknown_root() -> None:
    client = CFTCClient()
    with pytest.raises(ValueError, match="not recognised"):
        client.get_disaggregated("xyz")


@pytest.mark.vcr
def test_get_disaggregated_rows_are_sorted_by_date() -> None:
    client = CFTCClient()
    df = client.get_disaggregated("lco", start=date(2026, 7, 1), end=date(2026, 8, 31))

    assert not df.empty
    assert df["date"].is_monotonic_increasing
