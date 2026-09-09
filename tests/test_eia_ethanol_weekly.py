# tests/test_eia_ethanol_weekly.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_ethanol_weekly


@pytest.mark.vcr
def test_ethanol_returns_valid_ts_long_for_every_region() -> None:
    df = pull_ethanol_weekly.pull_ethanol(pull_ethanol_weekly.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["freq"]) == {"weekly"}
    # Every requested region must return rows. A region that silently returns nothing
    # would leave a hole in the blending picture that no error reports.
    assert set(df["series_id"]) == set(pull_ethanol_weekly.ETHANOL)


@pytest.mark.vcr
def test_all_five_padds_are_covered_not_four() -> None:
    # Plan 31A's Task 0 corrected the spec on exactly this: the route carries PADD1-5,
    # and an earlier draft said PADD1-4. Under-ingesting PADD5 (the West Coast) was the
    # named cost of getting this wrong.
    df = pull_ethanol_weekly.pull_ethanol(pull_ethanol_weekly.EIAClient())

    assert len(pull_ethanol_weekly.ETHANOL) == 6, "US plus PADD1-5"
    geos = set(df["geo"])
    for padd in ("PADD1", "PADD2", "PADD3", "PADD4", "PADD5"):
        assert padd in geos, f"{padd} missing -- geo resolved to {sorted(geos)}"
    # Never the literal "NA" this route family returns in area-name on some routes.
    assert "NA" not in geos


def test_regions_are_named_constants_not_positional() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing.
    assert pull_ethanol_weekly.US in pull_ethanol_weekly.ETHANOL
    assert pull_ethanol_weekly.PADD5 in pull_ethanol_weekly.ETHANOL
    assert len(set(pull_ethanol_weekly.ETHANOL)) == len(pull_ethanol_weekly.ETHANOL)
