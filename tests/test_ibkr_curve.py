"""IBKR MCP curve parsing. No cassettes exist for this source and none can: vcrpy records
HTTP made from Python, and this data arrives through an MCP tool, never through Python's
HTTP stack. The fixture under tests/fixtures/futures/ is a trimmed real response instead."""

from __future__ import annotations

import pandas as pd
import pytest
from pipelines.futures.client import looks_like_rank_code
from pipelines.futures.ibkr_curve import (
    REJECTION_REASONS,
    bars_from_history,
    contract_code_from_month,
    liquid_bars,
)


def test_contract_code_from_month_covers_every_month_letter() -> None:
    codes = [contract_code_from_month(f"2026{month:02d}") for month in range(1, 13)]
    assert codes == [
        "f2026", "g2026", "h2026", "j2026", "k2026", "m2026",
        "n2026", "q2026", "u2026", "v2026", "x2026", "z2026",
    ]


def test_every_derived_code_clears_the_rank_namespace_guard() -> None:
    """A two-digit year would collide: January is "f", so f27 reads as rank 27. Eight such
    series were live in the lake before that was caught."""
    for year in (2026, 2027, 2030, 2036):
        for month in range(1, 13):
            code = contract_code_from_month(f"{year}{month:02d}")
            assert not looks_like_rank_code(code), code


def test_contract_code_rejects_a_malformed_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("2026-12")


def test_contract_code_rejects_an_impossible_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("202613")


def test_bars_from_history_reads_the_parallel_arrays_and_normalises_to_dates() -> None:
    history = {
        "time": ["2026-09-10T13:30:00Z", "2026-09-11T13:30:00Z"],
        "open": [92.39, 90.76],
        "high": [94.87, 91.81],
        "low": [91.04, 90.66],
        "close": [93.93, 91.43],
        "volume": [34571, 21699],
    }
    bars = bars_from_history(history)
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]
    # A daily bar is stamped 13:30Z by the API; the lake's daily convention is the date.
    assert list(bars["ts"]) == [pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")]
    assert bars["close"].dtype == "float64"


def test_bars_from_history_tolerates_an_empty_response() -> None:
    bars = bars_from_history({})
    assert bars.empty
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_liquid_bars_rejects_the_real_zero_volume_stale_print() -> None:
    """CLZ7's 2021-12 bar is 57.31 four times on volume 0 -- a carried reference price,
    not a market. Confirmed live 2026-10-10."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-12-01", "2026-10-01"]),
            "open": [57.31, 75.17],
            "high": [57.31, 77.89],
            "low": [57.31, 74.45],
            "close": [57.31, 77.39],
            "volume": [0.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-01")]
    assert rejected["stale_print"] == 1
    assert rejected["zero_volume"] == 0  # counted once, under the more specific reason


def test_liquid_bars_counts_a_plain_zero_volume_bar_separately() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2022-01-03"]),
            "open": [59.12], "high": [62.25], "low": [59.07], "close": [61.95],
            "volume": [0.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert kept.empty
    assert rejected["zero_volume"] == 1
    assert rejected["stale_print"] == 0


def test_liquid_bars_left_trims_rather_than_dropping_the_contract() -> None:
    """A far-dated contract runs illiquid then liquid as it approaches the front. Keep the
    liquid tail; drop the dead beginning."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-11-01", "2021-12-01", "2026-09-01", "2026-10-01"]),
            "open": [56.5, 57.31, 71.16, 75.17],
            "high": [59.95, 57.31, 75.80, 77.89],
            "low": [56.5, 57.31, 70.10, 74.45],
            "close": [60.13, 57.31, 75.44, 77.39],
            "volume": [2.0, 0.0, 223836.0, 98071.0],
        }
    )
    kept, _ = liquid_bars(bars)
    assert len(kept) == 3
    assert kept["ts"].min() == pd.Timestamp("2021-11-01")


def test_liquid_bars_rejects_a_missing_or_non_positive_close() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"]),
            "open": [75.17, 75.00, 0.0],
            "high": [77.89, 76.00, 76.00],
            "low": [74.45, 74.00, 74.00],
            "close": [None, -1.0, 75.50],
            "volume": [98071.0, 98071.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-05")]
    assert rejected["no_close"] == 1
    assert rejected["non_positive_close"] == 1


def test_every_rejection_reason_is_reported_even_when_zero() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01"]),
            "open": [75.17], "high": [77.89], "low": [74.45], "close": [77.39],
            "volume": [98071.0],
        }
    )
    _, rejected = liquid_bars(bars)
    assert set(rejected) == set(REJECTION_REASONS)
    assert sum(rejected.values()) == 0
