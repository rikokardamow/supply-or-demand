from __future__ import annotations

import pandas as pd
import pytest
import requests
from core import storage
from core.failures import PartialFailureError
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
    # A regression to national-only would still pass every assertion above -- this is
    # the one that would actually catch it. Spec 30's chart needs the state-level
    # dispersion, not a single national average (pipelines/eia/NOTES.md).
    assert set(df["geo"]) == set(pull_prices.GENERATOR_FUEL_LOCATIONS)


@pytest.mark.vcr
def test_generator_fuel_cost_key_is_the_dollar_denominated_cost_series() -> None:
    # GENERATOR_FUEL[0] is load-bearing: a dashboard page reads it to pick the cost
    # series for a $/MMBtu chart. Reordering the plain list would silently plot
    # consumption-for-eg (thousand Mcf) on that axis instead -- nothing would raise,
    # the chart would just be wrong. Pin both the constant's identity and its pulled
    # unit so a reorder or rename fails loudly here, not silently on a chart.
    assert pull_prices.GENERATOR_FUEL[0] == pull_prices.GENERATOR_FUEL_COST_KEY

    df = pull_prices.pull_group(
        pull_prices.EIAClient(),
        pull_prices.GENERATOR_FUEL_ROUTE,
        [pull_prices.GENERATOR_FUEL_COST_KEY],
        "monthly",
    )

    assert not df.empty
    assert all("dollar" in u.lower() for u in df["unit"].unique())


@pytest.mark.default_cassette("test_generator_fuel_cost_returns_valid_ts_long")
@pytest.mark.vcr
def test_generator_fuel_series_id_helper_matches_the_client_minted_id() -> None:
    # The client mints this id inline in EIAClient.get_operational_series; a dashboard
    # page re-derives the same string independently, including a hardcoded frequency
    # code. Asserted against a real client-produced series_id (not a hardcoded
    # literal) so drift in either the client's minting logic or _FREQUENCY_CODES is
    # caught here rather than surfacing as "no data" on a chart. Reuses the existing
    # test_generator_fuel_cost_returns_valid_ts_long cassette -- same pull_group call,
    # no new network recording needed.
    df = pull_prices.pull_group(
        pull_prices.EIAClient(),
        pull_prices.GENERATOR_FUEL_ROUTE,
        pull_prices.GENERATOR_FUEL,
        "monthly",
    )
    us_cost_row = df[(df["geo"] == "US") & (df["unit"].str.contains("dollar", case=False))].iloc[0]

    assert (
        pull_prices.generator_fuel_series_id(pull_prices.GENERATOR_FUEL_COST_KEY, "US")
        == us_cost_row["series_id"]
    )


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
                "series_id": ["X"],
                "source": ["eia"],
                "ts": [pd.Timestamp("2026-01-01")],
                "value": [1.0],
                "unit": ["$/bbl"],
                "geo": ["US"],
                "freq": [frequency],
                "revision_date": [pd.Timestamp("2026-01-02")],
            }
        )

    monkeypatch.setattr(pull_prices.EIAClient, "get_series", fake_get_series)

    frames = pull_prices.pull_all(
        [("petroleum/pri/rac2", ["A"], "monthly"), ("petroleum/pri/gnd", ["B"], "weekly")]
    )

    assert len(calls) == 2, "the second route must still be attempted"
    assert len(frames) == 1, "only the surviving route yields a frame"


def test_main_raises_when_every_route_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # main() is correct today -- record_failure inside failure_scope means
    # raise_if_any() fires even on the "if not frames: return" path -- but nothing in
    # this suite exercised a wholly-failed run, so a regression to a bare try/except
    # that swallows every failure and returns normally would not be caught.
    def boom(*args: object, **kwargs: object) -> pd.DataFrame:
        raise requests.exceptions.ConnectionError("eia down")

    monkeypatch.setattr(pull_prices.EIAClient, "get_series", boom)
    monkeypatch.setattr(pull_prices.EIAClient, "get_operational_series", boom)

    with pytest.raises(PartialFailureError):
        pull_prices.main()


def test_a_revised_value_replaces_its_predecessor(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # PMM and EPM both restate prior months. write_ts_long dedups on
    # (series_id, ts) sorted by revision_date, so the later pull must win --
    # not produce two rows for the same month.
    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    def row(value: float, revised: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "series_id": ["R0000____3"],
                "source": ["eia"],
                "ts": [pd.Timestamp("2026-01-01")],
                "value": [value],
                "unit": ["$/bbl"],
                "geo": ["US"],
                "freq": ["monthly"],
                "revision_date": [pd.Timestamp(revised)],
            }
        )

    storage.write_ts_long(row(70.0, "2026-02-01"), source="eia")
    storage.write_ts_long(row(72.5, "2026-03-01"), source="eia")

    got = storage.read_ts_long(series_ids=["R0000____3"])
    assert len(got) == 1, "a revision must replace, not duplicate"
    assert got.iloc[0]["value"] == 72.5
