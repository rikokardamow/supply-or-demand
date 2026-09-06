from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from core.storage import (
    LAKE_ROOT,
    last_ts_by_source,
    read_events,
    read_flows,
    read_ts_long,
    write_events,
    write_flows,
    write_ts_long,
)


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


def test_read_ts_long_is_not_corrupted_by_an_int64_typed_value_column_in_another_source() -> (
    None
):
    """Regression test for a real, confirmed-live incident: `pipelines/opec_momr`'s
    Baker Hughes rig counts are genuinely whole numbers, and a DataFrame column of
    only whole-number floats can end up written with a physically int64-typed
    parquet column if a caller ever bypasses write_ts_long's own float64 coercion
    (as this test deliberately does, to reproduce the original bug's exact
    conditions). Reading the *other*, correctly double-typed source alongside it
    must still return real decimal values, not have them silently truncated to
    whichever type DuckDB's cross-file schema resolution happens to pick."""
    intlike_dir = LAKE_ROOT / "ts_long" / "source=intsource" / "year=2024"
    intlike_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "series_id": ["INTSERIES"],
            "source": ["intsource"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "value": pd.array([500], dtype="int64"),  # bypasses write_ts_long on purpose
            "unit": ["count"],
            "geo": ["US"],
            "freq": ["weekly"],
            "revision_date": pd.to_datetime(["2024-01-02"]),
        }
    ).to_parquet(intlike_dir / "part-0.parquet", index=False)

    write_ts_long(_make_df(datetime(2024, 1, 2), 0.86371), source="floatsource")

    float_result = read_ts_long(series_ids=["TEST1"])
    assert float_result.iloc[0]["value"] == pytest.approx(0.86371)

    int_result = read_ts_long(series_ids=["INTSERIES"])
    assert int_result.iloc[0]["value"] == 500.0
    assert float_result["value"].dtype == "float64"
    assert int_result["value"].dtype == "float64"


def test_write_ts_long_tolerates_a_tz_aware_revision_date_against_a_tz_naive_partition() -> None:
    """Regression test for a real, confirmed-live incident (Spec 19 Session A):
    pipelines/cftc's own pull scripts build revision_date via datetime.now(UTC)
    (tz-aware) while an earlier session's pipelines/derived writes had already landed
    tz-naive rows (datetime.now(), no UTC) in the same partition. Combining the two
    without normalising first crashed _write_partitioned's own sort_values call with
    "TypeError: Cannot compare tz-naive and tz-aware timestamps" -- confirmed live
    against the real lake before this fix."""
    naive_dir = LAKE_ROOT / "ts_long" / "source=testsrc" / "year=2024"
    naive_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "series_id": ["TEST1"],
            "source": ["testsrc"],
            "ts": pd.to_datetime(["2024-01-01"]),
            "value": [50.0],
            "unit": ["mb"],
            "geo": ["US"],
            "freq": ["weekly"],
            "revision_date": pd.to_datetime(["2024-01-01"]),  # tz-naive, written directly
        }
    ).to_parquet(naive_dir / "part-0.parquet", index=False)

    tz_aware_df = _make_df(datetime(2024, 1, 2), 100.0)
    tz_aware_df["revision_date"] = tz_aware_df["revision_date"].dt.tz_localize("UTC")
    write_ts_long(tz_aware_df, source="testsrc")  # must not raise

    result = read_ts_long(series_ids=["TEST1"])
    assert len(result) == 1
    assert result.iloc[0]["value"] == 100.0


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


def _make_events_df(event_id: str, tags: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": [event_id],
            "ts": pd.to_datetime(["2026-09-01"]),
            "headline": ["Refinery fire in Rotterdam"],
            "source": ["gdelt"],
            "url": [f"https://example.com/{event_id}"],
            "tags": [tags],
            "geo": ["NL"],
            "commodity": ["crude"],
            "severity": [1],
            "language": ["English"],
        }
    )


def test_read_events_fills_null_for_a_column_missing_from_every_on_disk_file() -> None:
    """Regression test for a real, confirmed-live gotcha found while adding
    `language` to EVENTS_SCHEMA: `union_by_name=true` only NULL-fills a column that
    exists in at least *one* scanned file -- if a column is absent from EVERY file
    (as `language` genuinely was, project-wide, until the first post-schema-change
    write), referencing it in the outer SELECT used to raise a DuckDB Binder Error
    rather than reading cleanly. Reproduces that exact condition by writing a raw
    parquet file with no `language` column at all, bypassing write_events."""
    old_dir = LAKE_ROOT / "events" / "source=gdelt" / "year=2026"
    old_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "event_id": ["e_old"],
            "ts": pd.to_datetime(["2026-01-01"]),
            "headline": ["Old row from before language existed"],
            "source": ["gdelt"],
            "url": ["https://example.com/e_old"],
            "tags": [["outage"]],
            "geo": ["NL"],
            "commodity": ["crude"],
            "severity": [1],
        }
    ).to_parquet(old_dir / "part-0.parquet", index=False)

    result = read_events()

    assert len(result) == 1
    assert result.iloc[0]["language"] is None


def test_events_round_trip_preserves_list_typed_tags() -> None:
    write_events(_make_events_df("e1", ["outage"]), source="gdelt")

    result = read_events()

    assert len(result) == 1
    # DuckDB hands back a list-typed column as a numpy array, not a plain Python list
    # (confirmed live) -- list(...) normalises before comparing.
    assert list(result.iloc[0]["tags"]) == ["outage"]


def test_events_dedup_keeps_last_row_per_event_id() -> None:
    write_events(_make_events_df("e1", ["outage"]), source="gdelt")
    write_events(_make_events_df("e1", ["outage", "sanctions"]), source="gdelt")

    result = read_events()

    assert len(result) == 1
    assert list(result.iloc[0]["tags"]) == ["outage", "sanctions"]


def test_read_events_filters_by_commodity() -> None:
    crude = _make_events_df("e1", ["outage"])
    gas = _make_events_df("e2", ["supply"])
    gas["commodity"] = "gas"
    write_events(pd.concat([crude, gas], ignore_index=True), source="gdelt")

    result = read_events(commodity="gas")

    assert len(result) == 1
    assert result.iloc[0]["event_id"] == "e2"


def test_last_ts_by_source_returns_one_row_per_source() -> None:
    early = _make_df(datetime(2024, 1, 1), value=1.0)
    late = _make_df(datetime(2024, 6, 1), value=2.0)
    late["series_id"] = ["TEST2"]  # a distinct series, so dedup keeps both rows
    other = _make_df(datetime(2024, 3, 1), value=3.0)
    other["source"] = ["othersrc"]

    write_ts_long(early, source="testsrc")
    write_ts_long(late, source="testsrc")
    write_ts_long(other, source="othersrc")

    result = last_ts_by_source("ts_long", "revision_date").set_index("source")

    assert set(result.index) == {"testsrc", "othersrc"}
    assert result.loc["testsrc", "last_seen"] == pd.Timestamp("2024-06-01")
    assert result.loc["othersrc", "last_seen"] == pd.Timestamp("2024-03-01")


def test_last_ts_by_source_is_empty_when_the_dataset_has_no_files() -> None:
    result = last_ts_by_source("ts_long", "revision_date")

    assert result.empty
    assert list(result.columns) == ["source", "last_seen"]


def test_last_ts_by_source_rejects_a_column_outside_the_schema() -> None:
    with pytest.raises(ValueError, match="not a column of the 'flows' schema"):
        last_ts_by_source("flows", "revision_date")  # flows has no revision_date
