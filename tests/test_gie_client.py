from __future__ import annotations

from datetime import date

import pytest
from core.schemas import validate_ts_long
from pipelines.gie.client import GIEClient

EXPECTED_SERIES = {
    "agsi.DE.full_pct",
    "agsi.DE.gas_in_storage",
    "agsi.DE.injection",
    "agsi.DE.withdrawal",
    "agsi.DE.working_gas_volume",
}


@pytest.mark.vcr
def test_get_agsi_history_returns_ts_long_conformant_dataframe() -> None:
    client = GIEClient()
    df = client.get_agsi_history("DE", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    validate_ts_long(df)
    assert set(df["series_id"]) == EXPECTED_SERIES
    assert (df["geo"] == "DE").all()
    assert (df["source"] == "gie").all()
    assert (df["freq"] == "D").all()
