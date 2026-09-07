from __future__ import annotations

import pandas as pd
import pytest
from core.failures import PartialFailureError
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
    # A region silently returning zero rows is a missing denominator -- the entire
    # point of this pull -- so this must be strict equality, not a subset check.
    assert set(df["geo"]) == set(pull_gas_capacity.CAPACITY_GEO_MAP.values())
    # Capacity is published in MMcf; the storage volumes it denominates are Bcf --
    # a factor of 1,000 that every fullness_pct caller relies on. Confirmed live
    # against the cassette (972 rows): pin the exact string EIA returns so a
    # republish in a different unit fails loudly here, not silently on a chart.
    assert set(df["unit"]) == {"MMCF"}


def test_every_capacity_region_has_a_matching_storage_region() -> None:
    # The whole point of this pull is to give the storage volumes already in the
    # lake a denominator. A capacity region with no storage counterpart cannot be
    # turned into a fullness ratio, so the two maps must line up.
    #
    # No HTTP call happens here -- both maps are module-level dicts compared in
    # memory -- so this is not a cassette test.
    from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP

    capacity_regions = set(pull_gas_capacity.CAPACITY_GEO_MAP.values())
    storage_regions = set(STORAGE_GEO_MAP.values())
    assert capacity_regions <= storage_regions, (
        f"capacity regions with no storage counterpart: {capacity_regions - storage_regions}"
    )


def test_main_raises_when_no_capacity_rows_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty (or wholly missing) pull must not report success to the scheduler --
    # see core/failures.py's docstring on why a swallowed failure has to raise so the
    # exit status is honest. No cassette: pull_capacity is monkeypatched directly.
    empty = pd.DataFrame(
        columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
    )
    monkeypatch.setattr(pull_gas_capacity, "pull_capacity", lambda client: empty)

    with pytest.raises(PartialFailureError):
        pull_gas_capacity.main()


def test_fullness_pct_applies_the_mmcf_to_bcf_conversion() -> None:
    # Live-verified L48 figures (pipelines/eia/NOTES.md, 2026-09-06): 3,214 Bcf storage
    # against 4,748,719 MMcf capacity -> about 67.7%. The measured percentage drifts with
    # the injection season, so this pins the invariant and a wide band, never the exact
    # figure -- a hard-coded expectation would fail for the right reason at the wrong time.
    pct = pull_gas_capacity.fullness_pct(3214.0, 4_748_719.0)
    assert 0 < pct < 100
    assert 40 < pct < 95  # wide band around the ~67.7% reference, not a pinned value

    # The regression that matters: a naive unconverted division (forgetting the x1000)
    # must not be what this returns.
    naive = 3214.0 / 4_748_719.0 * 100.0
    assert pct != pytest.approx(naive)
