from __future__ import annotations

import pandas as pd
import pytest
from pipelines.macro.eurostat_client import EurostatESIClient


@pytest.mark.vcr
def test_get_esi_returns_real_data_for_all_six_geos() -> None:
    df = EurostatESIClient().get_esi()

    assert list(df.columns) == ["ts", "geo", "value"]
    assert not df.empty
    assert set(df["geo"]) == {"EU", "DE", "FR", "IT", "ES", "IE"}
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    # ESI is conventionally centred around 100 (long-run average), but the *full*
    # history (back to the early 1980s for some countries) includes genuine extremes
    # confirmed live -- Italy's ESI hit 38.4 in 1982 -- so only the latest value per
    # geo is checked for a plausible recent range, not the entire history.
    latest = df.sort_values("ts").groupby("geo").tail(1)
    assert (latest["value"] > 50).all() and (latest["value"] < 150).all()


@pytest.mark.vcr
def test_get_esi_can_filter_to_a_subset_of_geos() -> None:
    df = EurostatESIClient().get_esi(geos=["DE"])

    assert set(df["geo"]) == {"DE"}
