"""pipelines/derived/lng.py and its destination mapping. All figures synthetic."""

from __future__ import annotations

import pandas as pd
from core import lng_balance as lb
from pipelines.derived import lng as d

JUL = pd.Timestamp("2026-07-01")


def test_the_committed_destination_mapping_is_valid() -> None:
    mapping = pd.read_csv(d.DESTINATIONS_CSV)

    assert not mapping["destination"].duplicated().any()
    assert set(mapping["region"]) <= set(lb.REGIONS) - {"unmapped", "unallocated"}
    assert set(mapping["bloc"]) <= {"eu", "uk", "other"}
    assert mapping.set_index("destination").loc["united_kingdom", "bloc"] == "uk"


def test_build_rows_writes_regions_origins_and_both_mirrors() -> None:
    us = pd.DataFrame(
        {"kind": ["exports", "exports", "exports"], "destination": ["total", "germany",
         "united_kingdom"], "ts": JUL, "value": [2000.0, 1500.0, 500.0]}
    )  # fmt: skip
    eu_trade = pd.DataFrame(
        {"flow": "imports", "product": ["gas", "gas", "lng"], "partner": ["total", "us", "us"],
         "ts": JUL, "value": [42.0, 42.0, 40.0]}
    )  # fmt: skip
    uk_trade = pd.DataFrame(
        {"flow": "imports", "type": "lng", "country": ["usa"], "pipeline": "na", "ts": JUL,
         "value": [14.0]}
    )  # fmt: skip

    rows = d.build_rows(us, eu_trade, uk_trade, pd.read_csv(d.DESTINATIONS_CSV), JUL)
    get = rows.set_index("series_id")["value"]

    assert get["derived.lng.us_exports.europe.observed"] == 2000 * lb.MCM_PER_MMCF / 1000
    assert get["derived.lng.europe_imports.united_states.observed"] == 0.054
    assert get["derived.lng.mirror_uk.europe_reported.observed"] == 0.014
    assert "derived.lng.mirror_eu.us_reported.observed" in get.index
