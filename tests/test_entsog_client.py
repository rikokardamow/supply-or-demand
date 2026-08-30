from __future__ import annotations

from datetime import date

import pytest
from pipelines.entsog.client import ENTSOGClient


@pytest.mark.vcr
def test_get_operator_point_directions_returns_full_directory() -> None:
    client = ENTSOGClient()
    directory = client.get_operator_point_directions()

    assert not directory.empty
    assert {"pointKey", "pointLabel", "directionKey"} <= set(directory.columns)
    # Confirms limit=-1 actually bypasses the ~100-row default page.
    assert len(directory) > 100


@pytest.mark.vcr
def test_get_physical_flow_returns_raw_kwh_values() -> None:
    client = ENTSOGClient()
    df = client.get_physical_flow(
        "ITP-00105", "entry", date(2026, 8, 25), date(2026, 8, 28)
    )

    assert not df.empty
    assert set(df.columns) == {"ts", "value_kwh_d"}
    assert df["value_kwh_d"].dtype.kind == "f"
    # Sanity-check the magnitude is kWh/d, not already GWh/d (a real Emden value seen live
    # was ~2.9e8 kWh/d) — catches an accidental unit-conversion regression in the client.
    assert df["value_kwh_d"].iloc[0] > 1_000_000


@pytest.mark.vcr
def test_get_physical_flow_returns_empty_for_a_point_with_no_data() -> None:
    # ITP-00075 (Emden NPT, entry) has no Physical Flow data for 2026 despite the
    # directory marking it hasData=True — ENTSOG returns 404 {"message": "No result
    # found"} rather than 200 with an empty array. Confirmed live; must not raise.
    client = ENTSOGClient()
    df = client.get_physical_flow(
        "ITP-00075", "entry", date(2026, 1, 1), date(2026, 8, 28)
    )

    assert df.empty
    assert list(df.columns) == ["ts", "value_kwh_d"]


@pytest.mark.vcr
def test_get_physical_flow_drops_rows_with_empty_string_value() -> None:
    # ITP-00519 (Dunkerque DKB, entry) returns a row per day but with value="" for
    # every day in a real 31-day range — confirmed live. Must not crash on float("").
    client = ENTSOGClient()
    df = client.get_physical_flow(
        "ITP-00519", "entry", date(2026, 7, 30), date(2026, 8, 29)
    )

    assert df.empty
    assert list(df.columns) == ["ts", "value_kwh_d"]


@pytest.mark.vcr
def test_get_nomination_returns_raw_kwh_values() -> None:
    # Same endpoint/shape as get_physical_flow, just indicator=Nomination — confirms
    # the client's indicator param actually reaches the request (not hardcoded).
    client = ENTSOGClient()
    df = client.get_nomination("ITP-00105", "entry", date(2026, 8, 25), date(2026, 8, 28))

    assert not df.empty
    assert set(df.columns) == {"ts", "value_kwh_d"}
    assert df["value_kwh_d"].dtype.kind == "f"
