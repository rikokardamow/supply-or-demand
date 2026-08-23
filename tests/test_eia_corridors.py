from __future__ import annotations

from pipelines.eia.corridors import parse_crude_padd_corridors

SAMPLE_FACETS = [
    {
        "id": "MCRMPP2P31",
        "name": "Midwest (PADD 2) Receipts by Pipeline from Gulf Coast (PADD 3) "
        "of Crude Oil (Thousand Barrels)",
    },
    {
        "id": "MTTMX_R40-R50_1",
        "name": "Rocky Mountain (PADD 4) Receipts by Pipeline, Tanker, Barge and "
        "Rail from West Coast (PADD 5) of Crude Oil and Petroleum Products "
        "(Thousand Barrels)",
    },
    {
        "id": "MCRMT1ZP31",
        "name": "Lower Atlantic (PADD 1C) Receipts by Tanker and Barge from Gulf "
        "Coast (PADD 3) of Crude Oil (Thousand Barrels)",
    },
]


def test_parses_clean_padd_to_padd_crude_corridor() -> None:
    corridors = parse_crude_padd_corridors(SAMPLE_FACETS, mode="pipeline")

    assert corridors["MCRMPP2P31"] == ("PADD3", "PADD2", "pipeline")


def test_excludes_combined_crude_and_products_series() -> None:
    corridors = parse_crude_padd_corridors(SAMPLE_FACETS, mode="pipeline")

    assert "MTTMX_R40-R50_1" not in corridors


def test_excludes_padd_subregion_series() -> None:
    corridors = parse_crude_padd_corridors(SAMPLE_FACETS, mode="tanker_barge")

    assert "MCRMT1ZP31" not in corridors


def test_only_the_clean_series_survives() -> None:
    corridors = parse_crude_padd_corridors(SAMPLE_FACETS, mode="pipeline")

    assert len(corridors) == 1
