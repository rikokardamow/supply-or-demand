"""Discovers main-PADD-to-PADD crude oil movement corridors from EIA's facet
listings, by parsing series NAMES rather than guessing series ID conventions (which
vary inconsistently across the pipe/tb/rail routes — see pipelines/eia/CLAUDE.md)."""

from __future__ import annotations

import re

from pipelines.eia.client import EIAClient

_CRUDE_PADD_PATTERN = re.compile(
    r"^.*\(PADD (\d)\) Receipts by .+ from .*\(PADD (\d)\) of Crude Oil \(Thousand Barrels\)$"
)

ROUTES_BY_MODE = {
    "pipeline": "petroleum/move/pipe",
    "tanker_barge": "petroleum/move/tb",
    "rail": "petroleum/move/rail",
}


def parse_crude_padd_corridors(
    facets: list[dict[str, str]], mode: str
) -> dict[str, tuple[str, str, str]]:
    """Map series id -> (from_node, to_node, mode) for series matching the clean
    "<dest> (PADD N) Receipts ... from <orig> (PADD M) of Crude Oil" pattern.
    Deliberately excludes PADD sub-regions (1A/1B/1C) and combined crude+products
    series — they don't match this exact pattern, by design."""
    corridors: dict[str, tuple[str, str, str]] = {}
    for facet in facets:
        match = _CRUDE_PADD_PATTERN.match(facet["name"])
        if not match:
            continue
        dest, orig = match.group(1), match.group(2)
        corridors[facet["id"]] = (f"PADD{orig}", f"PADD{dest}", mode)
    return corridors


def discover_all_corridors(client: EIAClient) -> dict[str, dict[str, tuple[str, str, str]]]:
    """Returns {route: {series_id: (from_node, to_node, mode)}}, one entry per mode."""
    return {
        route: parse_crude_padd_corridors(client.list_series(route), mode)
        for mode, route in ROUTES_BY_MODE.items()
    }
