from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_gas_capacity


@pytest.mark.vcr
def test_capacity_returns_valid_ts_long_with_real_regions() -> None:
    df = pull_gas_capacity.pull_capacity(pull_gas_capacity.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    # geo must be a real region label, never the literal "NA" this route family
    # returns in area-name (the quirk pull_gas_storage.py already works around).
    assert "NA" not in set(df["geo"])
    assert set(df["geo"]).issubset(set(pull_gas_capacity.CAPACITY_GEO_MAP.values()))


@pytest.mark.vcr
def test_every_capacity_region_has_a_matching_storage_region() -> None:
    # The whole point of this pull is to give the storage volumes already in the
    # lake a denominator. A capacity region with no storage counterpart cannot be
    # turned into a fullness ratio, so the two maps must line up.
    from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP

    capacity_regions = set(pull_gas_capacity.CAPACITY_GEO_MAP.values())
    storage_regions = set(STORAGE_GEO_MAP.values())
    assert capacity_regions <= storage_regions, (
        f"capacity regions with no storage counterpart: {capacity_regions - storage_regions}"
    )
