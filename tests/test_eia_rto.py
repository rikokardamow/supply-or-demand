from __future__ import annotations

from pipelines.eia import rto


def test_the_two_markets_this_item_exists_for_are_present() -> None:
    # The spec's entire justification for item 2: gridstatus reaches CAISO and NYISO
    # only -- ERCOT is blocked by Incapsula (confirmed live 403) and PJM needs a Data
    # Miner 2 key the project does not hold. If these two are missing, this pipeline
    # has no reason to exist.
    assert rto.ERCOT in rto.RTO_RESPONDENTS
    assert rto.PJM in rto.RTO_RESPONDENTS


def test_respondents_are_named_constants_and_unique() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing. Selected by name, never index.
    assert len(set(rto.RTO_RESPONDENTS)) == len(rto.RTO_RESPONDENTS)
    for name in (rto.ERCOT, rto.PJM, rto.MISO, rto.SPP, rto.CAISO, rto.NYISO, rto.ISNE):
        assert name in rto.RTO_RESPONDENTS


def test_region_series_id_is_deterministic_and_carries_both_facets() -> None:
    row = {"respondent": "ERCO", "type": "D", "period": "2026-09-01T00"}
    assert rto.region_series_id(row) == "RTO.REGION.ERCO.D.H"
    # Deterministic: the same row must always mint the same id, because the id is
    # permanent once written to the lake.
    assert rto.region_series_id(row) == rto.region_series_id(dict(row))


def test_fuel_series_id_is_distinct_from_region_series_id() -> None:
    # Both routes carry a `respondent`, and `type=NG` (net generation) is the same two
    # characters as `fueltype=NG` (natural gas). If the two schemes collided, a
    # fuel-mix value would overwrite a net-generation value in the lake, silently.
    region = rto.region_series_id({"respondent": "PJM", "type": "NG"})
    fuel = rto.fuel_series_id({"respondent": "PJM", "fueltype": "NG"})
    assert region != fuel
    assert fuel == "RTO.FUEL.PJM.NG.H"


def test_natural_gas_fuel_type_is_named() -> None:
    # Gas-fired generation is the whole gas-demand signal this item feeds.
    assert rto.NATURAL_GAS in rto.FUEL_TYPES
