from __future__ import annotations

import pandas as pd
from pipelines.gridstatus_iso.transforms import net_load


def _hours(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-09-01", periods=n, freq="h")


def test_net_load_subtracts_both_renewable_sources() -> None:
    idx = _hours(3)
    result = net_load(
        load=pd.Series([1000.0, 1100.0, 1200.0], index=idx),
        wind=pd.Series([200.0, 250.0, 300.0], index=idx),
        solar=pd.Series([100.0, 150.0, 50.0], index=idx),
    )

    assert result.tolist() == [700.0, 700.0, 850.0]


def test_a_missing_renewable_timestamp_counts_as_zero_not_as_a_dropped_hour() -> None:
    """The documented decision in this module, and the one worth pinning: an hour with no
    wind reading means no wind generation to subtract, so net load equals load. Dropping
    the hour instead would silently shorten the series and put a hole in every chart and
    aggregate built on it."""
    idx = _hours(3)
    result = net_load(
        load=pd.Series([1000.0, 1100.0, 1200.0], index=idx),
        wind=pd.Series([200.0], index=idx[:1]),  # only the first hour reported
        solar=pd.Series([100.0, 150.0, 50.0], index=idx),
    )

    assert len(result) == 3  # never shorter than `load`
    assert result.tolist() == [700.0, 950.0, 1150.0]


def test_the_result_is_indexed_by_load_not_by_the_renewables() -> None:
    # A renewable series covering hours load doesn't have must not extend the result --
    # net load is only defined where there is a load reading to net against.
    idx = _hours(2)
    result = net_load(
        load=pd.Series([1000.0, 1100.0], index=idx),
        wind=pd.Series([10.0, 20.0, 30.0], index=_hours(3)),
        solar=pd.Series([1.0, 2.0, 3.0], index=_hours(3)),
    )

    assert result.index.equals(idx)
    assert result.tolist() == [989.0, 1078.0]


def test_an_empty_load_series_yields_an_empty_result() -> None:
    empty: pd.Series = pd.Series(dtype="float64", index=pd.DatetimeIndex([]))
    result = net_load(load=empty, wind=empty, solar=empty)

    assert result.empty
