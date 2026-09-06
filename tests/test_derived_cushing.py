from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import pytest
from core.schemas import TS_LONG_SCHEMA
from core.storage import read_ts_long, write_ts_long
from pipelines.derived import cushing


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _ts_long(series_id: str, ts: pd.DatetimeIndex, values: list[float], freq: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": series_id,
            "source": "eia",
            "ts": ts,
            "value": values,
            "unit": "mbbl",
            "geo": "OK",
            "freq": freq,
            "revision_date": pd.Timestamp("2026-09-01"),
        }
    )


def _seed_inputs() -> None:
    weeks = pd.date_range("2025-01-03", periods=12, freq="7D")
    stocks = [20_000.0 + 500 * i for i in range(len(weeks))]
    write_ts_long(_ts_long(cushing.STOCKS_SERIES_ID, weeks, stocks, "W"), source="eia")

    # Semi-annual, and deliberately sparse -- cushing_utilisation forward-fills it onto
    # the weekly stocks index.
    caps = pd.DatetimeIndex(["2024-09-30", "2025-03-31"])
    write_ts_long(
        _ts_long(cushing.CAPACITY_SERIES_ID, caps, [98_000.0, 99_000.0], "semi-annual"),
        source="eia",
    )


def test_main_writes_both_derived_series_conforming_to_ts_long() -> None:
    _seed_inputs()

    cushing.main()

    written = read_ts_long(series_ids=["derived.cushing.util", "derived.cushing.util_decile"])
    assert not written.empty
    assert set(written["series_id"]) == {"derived.cushing.util", "derived.cushing.util_decile"}
    assert list(written.columns) == list(TS_LONG_SCHEMA.names)
    assert set(written["source"]) == {"derived"}
    assert set(written["unit"]) == {"ratio"}
    assert set(written["geo"]) == {"OK"}
    assert set(written["freq"]) == {"W"}


def test_utilisation_is_the_stocks_to_capacity_ratio() -> None:
    _seed_inputs()

    cushing.main()

    util = read_ts_long(series_ids=["derived.cushing.util"]).set_index("ts")["value"].sort_index()
    # First week: 20,000 against the 2024-09-30 capacity of 98,000, forward-filled.
    assert util.iloc[0] == pytest.approx(20_000 / 98_000)
    assert (util > 0).all() and (util < 1).all()


def test_deciles_stay_inside_one_to_ten() -> None:
    _seed_inputs()

    cushing.main()

    decile = read_ts_long(series_ids=["derived.cushing.util_decile"])["value"]
    assert decile.between(1, 10).all()


def test_main_does_nothing_when_an_input_series_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Capacity comes from a different pipeline on a different cadence
    (pipelines/eia_storage_capacity), so running this before that one has ever run is a
    real ordering, not a hypothetical. It must skip, not divide by an empty frame."""
    weeks = pd.date_range("2025-01-03", periods=4, freq="7D")
    write_ts_long(_ts_long(cushing.STOCKS_SERIES_ID, weeks, [20_000.0] * 4, "W"), source="eia")

    cushing.main()

    assert "missing stocks or capacity series" in capsys.readouterr().out
    assert read_ts_long(series_ids=["derived.cushing.util"]).empty


def test_rerunning_is_idempotent() -> None:
    """Registered in the wpsr cadence group, so it re-runs weekly over an overlapping
    window; write_ts_long's (series_id, ts) de-dup must keep that a no-op."""
    _seed_inputs()

    cushing.main()
    first = len(read_ts_long(series_ids=["derived.cushing.util"]))
    cushing.main()

    assert len(read_ts_long(series_ids=["derived.cushing.util"])) == first


def test_ingested_at_is_recorded_as_the_revision_date() -> None:
    _seed_inputs()
    before = pd.Timestamp(datetime.now())

    cushing.main()

    written = read_ts_long(series_ids=["derived.cushing.util"])
    assert (written["revision_date"] >= before.floor("s")).all()
