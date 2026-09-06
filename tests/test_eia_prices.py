from __future__ import annotations

import pandas as pd
import pytest
import requests
from core.schemas import validate_ts_long
from pipelines.eia import pull_prices


@pytest.mark.vcr
def test_refiner_acquisition_cost_returns_valid_ts_long() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "petroleum/pri/rac2", pull_prices.RAC, "monthly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["series_id"]).issubset(set(pull_prices.RAC))
    # Units are stored exactly as EIA publishes them, never converted at ingest.
    assert all("$" in u for u in df["unit"].unique())


@pytest.mark.vcr
def test_retail_prices_are_weekly_and_dollars_per_gallon() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "petroleum/pri/gnd", pull_prices.RETAIL, "weekly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert set(df["freq"]) == {"weekly"}


@pytest.mark.vcr
def test_landed_cost_uses_geo_map_for_gravity_bands() -> None:
    # petroleum/pri/land3 returns area-name as the literal string "NA" for every row
    # (confirmed live, pipelines/eia/NOTES.md) -- geo must come from LANDED_COST_GEO_MAP,
    # not _normalise_geo(area-name).
    df = pull_prices.pull_group(
        pull_prices.EIAClient(),
        "petroleum/pri/land3",
        pull_prices.LANDED_COST,
        "monthly",
        geo_map=pull_prices.LANDED_COST_GEO_MAP,
    )

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["series_id"]).issubset(set(pull_prices.LANDED_COST))
    assert set(df["geo"]) == set(pull_prices.LANDED_COST_GEO_MAP.values())
    assert "NA" not in set(df["geo"])
    assert all("$" in u for u in df["unit"].unique())


@pytest.mark.vcr
def test_gas_prices_carry_dollar_units_and_state_or_national_geo() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(), "natural-gas/pri/sum", pull_prices.GAS, "monthly"
    )

    validate_ts_long(df)
    assert not df.empty
    assert all("$" in u for u in df["unit"].unique())
    assert df["geo"].notna().all()


@pytest.mark.vcr
def test_generator_fuel_cost_returns_valid_ts_long() -> None:
    df = pull_prices.pull_group(
        pull_prices.EIAClient(),
        "electricity/electric-power-operational-data",
        pull_prices.GENERATOR_FUEL,
        "monthly",
    )

    validate_ts_long(df)
    assert not df.empty


def test_monthly_and_weekly_groups_are_disjoint() -> None:
    # A route pulled on both cadences would write the same rows twice under two
    # revision_dates -- harmless to the lake's dedup, but a real sign of confusion.
    monthly = {route for route, _, _ in pull_prices.MONTHLY_GROUPS}
    weekly = {route for route, _, _ in pull_prices.WEEKLY_GROUPS}
    assert monthly.isdisjoint(weekly)


def test_one_failing_route_does_not_abort_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pattern pipelines/adanos/pull_adanos.py established: per-route resilience,
    # not just per-request retry. One dead route must never cost the rest of the pull.
    calls: list[str] = []

    def fake_get_series(self, route, series, frequency, geo_map=None):  # type: ignore[no-untyped-def]
        calls.append(route)
        if route == "petroleum/pri/gnd":
            raise requests.exceptions.ConnectionError("gnd down")
        return pd.DataFrame(
            {
                "series_id": ["X"], "source": ["eia"], "ts": [pd.Timestamp("2026-01-01")],
                "value": [1.0], "unit": ["$/bbl"], "geo": ["US"], "freq": [frequency],
                "revision_date": [pd.Timestamp("2026-01-02")],
            }
        )

    monkeypatch.setattr(pull_prices.EIAClient, "get_series", fake_get_series)

    frames = pull_prices.pull_all(
        [("petroleum/pri/rac2", ["A"], "monthly"), ("petroleum/pri/gnd", ["B"], "weekly")]
    )

    assert len(calls) == 2, "the second route must still be attempted"
    assert len(frames) == 1, "only the surviving route yields a frame"
