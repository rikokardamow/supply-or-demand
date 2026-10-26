"""pipelines/eia/pull_lng_exports.py: series discovery by name. Names below are real EIA
facet names (confirmed live 2026-10-26), including every variant that once went unmatched.
They are kept verbatim, hence the long lines."""

# ruff: noqa: E501

from __future__ import annotations

import pytest
from pipelines.eia.client import EIAClient
from pipelines.eia.pull_lng_exports import ROUTE, TOTAL_SERIES, lng_series, slug

FACETS = [
    {"id": "A", "name": "Liquefied U.S. Natural Gas Exports by Vessel to Japan (Million Cubic Feet)"},
    {"id": "B", "name": "U.S. Liquefied Natural Gas Exports by Vessel  to Bahrain (Million Cubic Feet)"},
    {"id": "C", "name": "Liquefied U.S. Natural Gas Exports by Vessels to Spain (Million Cubic Feet)"},
    {"id": "D", "name": "Liquefied U.S. Natural Gas Exports by Vessel to United Kingdom (MMcf)"},
    {"id": "E", "name": "Liquefied U.S. Natural Gas Re-Exports to China (Million Cubic Feet)"},
    {"id": "F", "name": "Liquefied U.S. Natural Gas Exports by Truck to Mexico (Million Cubic Feet)"},
    {"id": "G", "name": "Price of Liquefied U.S. Natural Gas Exports by Vessel to Japan (Dollars per Thousand Cubic Feet)"},
    {"id": "H", "name": "U.S. Natural Gas Pipeline Exports to Mexico (Million Cubic Feet)"},
]  # fmt: skip


def test_every_naming_variant_maps_and_prices_never_do() -> None:
    ids = lng_series(FACETS)

    assert ids["A"] == "eia.lng.exports.japan"
    assert ids["B"] == "eia.lng.exports.bahrain"  # double space before "to"
    assert ids["C"] == "eia.lng.exports.spain"  # "Vessels"
    assert ids["D"] == "eia.lng.exports.united_kingdom"  # "(MMcf)" unit
    assert ids["E"] == "eia.lng.reexports.china"
    assert ids["F"] == "eia.lng.truck.mexico"
    assert "G" not in ids and "H" not in ids
    assert ids[TOTAL_SERIES] == "eia.lng.exports.total"


def test_slug() -> None:
    assert slug("Antigua and Barbuda") == "antigua_and_barbuda"


@pytest.mark.vcr
def test_live_facets_include_the_uk_under_its_mmcf_name() -> None:
    ids = lng_series(EIAClient().list_series(ROUTE))

    assert "eia.lng.exports.united_kingdom" in ids.values()
    assert sum(v.startswith("eia.lng.exports.") for v in ids.values()) > 40
