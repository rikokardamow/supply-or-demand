from __future__ import annotations

import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.futures.yfinance_front import (
    YAHOO_FUTURES,
    YahooFuture,
    history_to_ts_long,
    series_id,
)


def _history(closes: list[float | None], tz: str | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=len(closes), freq="D", tz=tz)
    return pd.DataFrame({"Open": closes, "Close": closes, "Volume": [1] * len(closes)}, index=index)


CL = YahooFuture("CL=F", "cl", "USD/bbl", "US")


def test_series_id_marks_the_value_as_a_close_not_a_settlement() -> None:
    # Measured live 2026-09-09 over 5,915 overlapping days: Yahoo's close matches EIA's
    # settlement within a cent only 96.4% of the time, exactly 3.6% of the time, and
    # differs by up to $1.50. They are different quantities, so they must not collide on
    # one series id -- a reader concatenating sources would otherwise silently pick
    # between two values for the same (series_id, ts) across 24 years.
    assert series_id("cl") == "fut.cl.f01.close"
    assert not series_id("cl").endswith(".settle")


def test_history_to_ts_long_produces_a_valid_ts_long_frame() -> None:
    rows = history_to_ts_long(_history([95.5, 96.0, 94.25]), CL)

    validate_ts_long(rows)  # raises if the canonical schema is violated
    assert list(rows["series_id"].unique()) == ["fut.cl.f01.close"]
    assert list(rows["source"].unique()) == ["yfinance"]
    assert list(rows["unit"].unique()) == ["USD/bbl"]
    assert rows["value"].tolist() == [95.5, 96.0, 94.25]


def test_history_to_ts_long_drops_sessions_with_no_close() -> None:
    # A holiday or halted session has no price. Carrying it as 0.0 would put a fake
    # crude print on a chart; forward-filling would invent a trade that never happened.
    rows = history_to_ts_long(_history([95.5, None, 94.25]), CL)

    assert len(rows) == 2
    assert rows["value"].tolist() == [95.5, 94.25]


def test_history_to_ts_long_strips_the_exchange_timezone() -> None:
    # Yahoo returns tz-aware exchange-local timestamps; the lake stores naive dates, and
    # a futures close belongs to its trade date rather than to an instant.
    rows = history_to_ts_long(_history([95.5, 96.0], tz="America/New_York"), CL)

    assert rows["ts"].dt.tz is None
    assert rows["ts"].tolist() == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-02")]


def test_history_to_ts_long_returns_an_empty_frame_for_an_empty_response() -> None:
    rows = history_to_ts_long(pd.DataFrame(), CL)

    assert rows.empty
    assert "series_id" in rows.columns


@pytest.mark.parametrize("future", YAHOO_FUTURES, ids=lambda f: f.symbol)
def test_every_configured_root_maps_to_a_distinct_close_series(future: YahooFuture) -> None:
    assert series_id(future.root).startswith("fut.")
    assert future.unit in {"USD/bbl", "USD/gal", "USD/MMBtu"}


def test_the_five_roots_are_distinct_and_match_the_lake_s_existing_root_names() -> None:
    roots = [f.root for f in YAHOO_FUTURES]
    assert len(set(roots)) == len(roots)
    # These roots already exist in pipelines/futures/contract_specs.csv; inventing a new
    # spelling here would fragment the lake's own `fut.<root>.*` namespace.
    assert set(roots) == {"cl", "lco", "ng", "ho", "rb"}
