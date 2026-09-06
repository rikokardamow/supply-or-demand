"""Invariants for this project's hand-maintained reference tables.

`pipelines/entsoe/zones.py`, `pipelines/news/queries.py`, `pipelines/adanos/tickers.py`
and `pipelines/weather/cities.csv` are curated by hand and imported at pull time. Nothing
validates them, so a typo in a zone code or an unbalanced population weight surfaces only
as a failed live API call or a quietly wrong aggregate, hours later and far from the edit.
These tests are the cheap check that edits stay self-consistent.
"""

from __future__ import annotations

import pytest
from pipelines.adanos.tickers import COMPARE_BATCH_SIZE, PLATFORMS, TICKERS
from pipelines.entsoe.zones import BORDERS, ZONES
from pipelines.news.queries import QUERIES
from pipelines.weather.cities import load_cities

# ---------------------------------------------------------------- entsoe zones/borders


def test_every_border_connects_two_known_zones() -> None:
    """A typo here ("DK1" for "DK_1") is not caught until pull_flows.py asks ENTSO-E for
    a zone that doesn't exist, mid-run."""
    unknown = {z for border in BORDERS for z in border if z not in ZONES}

    assert not unknown, f"borders reference zones missing from ZONES: {sorted(unknown)}"


def test_no_border_is_listed_twice_or_joins_a_zone_to_itself() -> None:
    assert all(a != b for a, b in BORDERS)
    undirected = {frozenset(b) for b in BORDERS}
    assert len(undirected) == len(BORDERS), "the same border appears in both directions"


def test_zone_list_has_no_duplicates() -> None:
    assert len(set(ZONES)) == len(ZONES)


def test_the_spec_s_minimum_border_count_still_holds() -> None:
    # specs/04_entsoe-eu-power.md's Definition of Done asks for >= 8 borders.
    assert len(BORDERS) >= 8


# ------------------------------------------------------------------------ news queries


def test_every_query_is_complete_and_non_empty() -> None:
    for spec in QUERIES:
        assert spec["commodity"], spec
        assert spec["event_type"], spec
        assert spec["query"].strip(), spec


def test_queries_cover_only_known_commodities() -> None:
    # `commodity` doubles as the tag written onto every resulting event row, and
    # apps/dashboard/pages/09_events.py filters on exactly these three.
    assert {q["commodity"] for q in QUERIES} <= {"crude", "gas", "power"}


def test_no_duplicate_commodity_event_type_pair() -> None:
    pairs = [(q["commodity"], q["event_type"]) for q in QUERIES]
    assert len(set(pairs)) == len(pairs)


def test_the_query_count_stays_within_the_spec_s_own_cap() -> None:
    # The spec caps this at 10; GDELT is queried once per entry on every daily pull.
    assert len(QUERIES) <= 10


# --------------------------------------------------------------------- adanos tickers


def test_ticker_symbols_are_unique_and_named() -> None:
    assert len(set(TICKERS)) == len(TICKERS)
    for symbol, name in TICKERS.items():
        assert symbol.strip() == symbol and symbol, f"{symbol!r} is blank or padded"
        assert name.strip(), f"{symbol} has no company name"


def test_every_ticker_was_confirmed_against_a_real_company_name() -> None:
    """pipelines/adanos/CLAUDE.md: a fake ticker still returns HTTP 200 with zeroed
    metrics, so a non-null company_name is the only real existence signal. A blank name
    here means the symbol was never actually confirmed."""
    unconfirmed = [s for s, name in TICKERS.items() if not name.strip()]

    assert not unconfirmed, f"tickers with no confirmed company name: {unconfirmed}"


def test_batching_constants_are_sane() -> None:
    assert COMPARE_BATCH_SIZE > 0
    assert PLATFORMS  # pull_adanos.py iterates these; an empty list is a silent no-op
    assert len(set(PLATFORMS)) == len(PLATFORMS)


# ------------------------------------------------------------------------ weather cities


def test_cities_csv_has_the_columns_every_consumer_reads() -> None:
    cities = load_cities()

    assert {"city", "country", "lat", "lon", "base", "population_weight"} <= set(cities.columns)
    assert not cities["city"].duplicated().any()


def test_population_weights_sum_to_one_within_each_region() -> None:
    """pipelines/weather/aggregate.py builds population-weighted regional degree days from
    these. Adding a city without rebalancing the others silently rescales the whole
    regional series rather than failing."""
    cities = load_cities()

    for base, group in cities.groupby("base"):
        assert group["population_weight"].sum() == pytest.approx(1.0, abs=1e-3), base


def test_every_city_carries_a_base_the_degree_day_code_understands() -> None:
    # pipelines/weather/degree_days.py maps exactly these two to 18C / 65F.
    assert set(load_cities()["base"]) <= {"c18", "f65"}


def test_coordinates_are_on_the_globe() -> None:
    cities = load_cities()

    assert cities["lat"].between(-90, 90).all()
    assert cities["lon"].between(-180, 180).all()
