from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from core.storage import read_flows, read_ts_long, write_flows, write_ts_long


def _make_df(revision_date: datetime, value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["TEST1"],
            "source": ["testsrc"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "value": [value],
            "unit": ["mb"],
            "geo": ["US"],
            "freq": ["weekly"],
            "revision_date": pd.to_datetime([revision_date]),
        }
    )


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_round_trip() -> None:
    df = _make_df(datetime(2024, 1, 2), 100.0)

    write_ts_long(df, source="testsrc")
    result = read_ts_long(series_ids=["TEST1"])

    assert len(result) == 1
    assert result.iloc[0]["value"] == 100.0


def test_dedup_keeps_latest_revision() -> None:
    old = _make_df(datetime(2024, 1, 2), 100.0)
    new = _make_df(datetime(2024, 1, 3), 200.0)

    write_ts_long(old, source="testsrc")
    write_ts_long(new, source="testsrc")

    result = read_ts_long(series_ids=["TEST1"])

    assert len(result) == 1
    assert result.iloc[0]["value"] == 200.0


def _make_flows_df(source: str, from_node: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": [source],
            "from_node": [from_node],
            "to_node": ["PADD1"],
            "value": [1.0],
            "unit": ["mb"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "mode": ["pipeline"],
        }
    )


def test_read_flows_filters_by_source() -> None:
    write_flows(_make_flows_df("eia", "PADD2"), source="eia")
    write_flows(_make_flows_df("entsog", "NO"), source="entsog")

    result = read_flows(source="eia")

    assert len(result) == 1
    assert result.iloc[0]["from_node"] == "PADD2"


def test_write_flows_replace_window_replaces_revised_rows() -> None:
    # flows has no revision_date column, so a revised value for an already-stored day
    # differs from the old row and plain full-row de-dup would keep both, silently
    # double-counting — replace_window must drop the stale row outright instead.
    old = pd.DataFrame(
        {
            "source": ["entsog"],
            "from_node": ["NO"],
            "to_node": ["DE"],
            "value": [100.0],
            "unit": ["GWh/d"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "mode": ["pipeline"],
        }
    )
    revised = old.copy()
    revised["value"] = [150.0]

    write_flows(old, source="entsog")
    write_flows(
        revised,
        source="entsog",
        replace_window=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")),
    )

    result = read_flows(source="entsog")

    assert len(result) == 1
    assert result.iloc[0]["value"] == 150.0


def test_write_flows_replace_window_leaves_rows_outside_window_untouched() -> None:
    day1 = pd.DataFrame(
        {
            "source": ["entsog"],
            "from_node": ["NO"],
            "to_node": ["DE"],
            "value": [100.0],
            "unit": ["GWh/d"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "mode": ["pipeline"],
        }
    )
    day2 = day1.copy()
    day2["ts"] = pd.to_datetime(["2024-01-02"])
    day2["value"] = [200.0]

    write_flows(pd.concat([day1, day2], ignore_index=True), source="entsog")
    write_flows(
        day1,
        source="entsog",
        replace_window=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")),
    )

    result = read_flows(source="entsog").sort_values("ts")

    assert len(result) == 2
    assert result.iloc[1]["value"] == 200.0


def test_write_flows_replace_window_keeps_pairs_missing_from_the_fresh_pull() -> None:
    # A daily re-pull only ever writes the pairs it successfully fetched this run --
    # one pair failing (a confirmed-live, routine occurrence) must not delete that
    # pair's still-good prior data just because it shares the replace_window with
    # pairs that did come back fresh. Caught live comparing two consecutive
    # pull_daily.py runs where one border failed on the second run only.
    no_de = pd.DataFrame(
        {
            "source": ["entsog"],
            "from_node": ["NO"],
            "to_node": ["DE"],
            "value": [100.0],
            "unit": ["GWh/d"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "mode": ["pipeline"],
        }
    )
    fr_es = pd.DataFrame(
        {
            "source": ["entsog"],
            "from_node": ["FR"],
            "to_node": ["ES"],
            "value": [50.0],
            "unit": ["GWh/d"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "mode": ["pipeline"],
        }
    )
    write_flows(pd.concat([no_de, fr_es], ignore_index=True), source="entsog")

    # Re-pull only refreshes FR->ES this time -- NO->DE's fetch failed and was
    # skipped by the pull script, so it's absent from what's being written.
    write_flows(
        fr_es,
        source="entsog",
        replace_window=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")),
    )

    result = read_flows(source="entsog")

    assert len(result) == 2
    no_de_row = result[(result["from_node"] == "NO") & (result["to_node"] == "DE")]
    assert len(no_de_row) == 1
    assert no_de_row.iloc[0]["value"] == 100.0
