# tests/test_eia_biofuels.py
from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_biofuels


@pytest.mark.vcr
def test_capacity_returns_valid_ts_long_for_every_fuel() -> None:
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["geo"]) == {"US"}
    assert set(df["series_id"]) == set(pull_biofuels.CAPACITY)


@pytest.mark.vcr
def test_renewable_diesel_capacity_is_present_and_named() -> None:
    # Renewable diesel capacity displacing petroleum diesel demand is the signal the
    # spec names for this item. Selected by name, never by index.
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())
    assert pull_biofuels.RENEWABLE_DIESEL in set(df["series_id"])


@pytest.mark.vcr
def test_feedstocks_return_valid_ts_long_for_every_series() -> None:
    df = pull_biofuels.pull_feedstocks(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    # A feedstock that silently returns nothing would understate feedstock competition,
    # which is the entire point of ingesting 26 series rather than a headline number.
    #
    # Real, live-confirmed exception (Task 2, 2026-09-09): 4 of the 26 feedstocks --
    # dedicated energy crops, biogas, municipal solid waste, yard/food waste -- report a
    # literal null value for every one of their recorded periods (2021-01 to 2026-06,
    # confirmed via a direct, unfiltered fetch of each series in isolation). EIAClient's
    # existing null-skip (client.py) therefore drops them to zero rows -- this is EIA
    # publishing no real data for these categories, not a bug in this pull or a truncated
    # FEEDSTOCKS list. See pipelines/eia/CLAUDE.md's Task 2 (31C) entry.
    always_null_feedstocks = {
        "M_EPOOBDAFD_YIFBP_NUS_MMLB",
        "M_EPOOBDBG_YIFBP_NUS_MMLB",
        "M_EPOOBDRFWM_YIFBP_NUS_MMLB",
        "M_EPOOBDRFWY_YIFBP_NUS_MMLB",
    }
    assert set(df["series_id"]) == set(pull_biofuels.FEEDSTOCKS) - always_null_feedstocks


def test_feedstock_list_is_the_full_set_and_has_no_duplicates() -> None:
    assert len(set(pull_biofuels.FEEDSTOCKS)) == len(pull_biofuels.FEEDSTOCKS)
    assert len(pull_biofuels.FEEDSTOCKS) == pull_biofuels.EXPECTED_FEEDSTOCK_COUNT
