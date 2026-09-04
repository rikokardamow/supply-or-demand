from __future__ import annotations

import pandas as pd
from core.schemas import validate_events
from pipelines.ofac.events_bridge import sanctions_to_events


def test_sanctions_to_events_maps_a_vessel_row_correctly() -> None:
    pull_date = pd.Timestamp("2026-09-01")
    newly_listed = pd.DataFrame(
        {
            "sanction_id": ["4238"],
            "name": ["MAR AZUL"],
            "entity_type": ["vessel"],
            "programs": [["CUBA", "CUBA-EO14404"]],
            "remarks": ["Vessel Registration Identification IMO 7406784."],
            "geo": ["CU"],
        }
    )

    events = sanctions_to_events(newly_listed, pull_date)

    validate_events(events)  # must conform to the existing events schema, no changes needed
    assert len(events) == 1
    row = events.iloc[0]
    assert row["source"] == "ofac"
    assert row["severity"] == 3  # vessel -> force-majeure-class tier
    assert row["geo"] == "CU"
    assert row["commodity"] == "crude"
    assert row["language"] == "unknown"
    assert "ofac_sanction" in row["tags"]
    assert "cuba" in row["tags"]
    assert row["url"] == "https://sanctionssearch.ofac.treas.gov/Details.aspx?id=4238"
    assert "MAR AZUL" in row["headline"]


def test_sanctions_to_events_infers_gas_commodity_from_keywords() -> None:
    pull_date = pd.Timestamp("2026-09-01")
    newly_listed = pd.DataFrame(
        {
            "sanction_id": ["999"],
            "name": ["National Gas Trading Company"],
            "entity_type": ["entity"],
            "programs": [["RUSSIA-EO14024"]],
            "remarks": [None],
            "geo": ["RU"],
        }
    )

    events = sanctions_to_events(newly_listed, pull_date)

    assert events.iloc[0]["commodity"] == "gas"
    assert events.iloc[0]["severity"] == 2
