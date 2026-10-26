"""Entrypoint: US LNG exports by destination country, monthly, from EIA.

    python -m pipelines.eia.pull_lng_exports

Route ``natural-gas/move/expc``. The series are discovered from the route's facet list by
name, never hard-coded: EIA adds a series when a new destination takes its first cargo.
Writes ``source="eia"``, ``geo="US"``, MMcf:

- ``eia.lng.exports.<destination>``: "U.S. Liquefied Natural Gas Exports by Vessel to X"
- ``eia.lng.reexports.<destination>``: "U.S. Liquefied Natural Gas Re-Exports to X"
  (foreign LNG reloaded in the US; small)
- ``eia.lng.truck.<destination>``: LNG by truck (Mexico, Canada); not seaborne
- ``eia.lng.exports.total``: ``N9133US2``, "Liquefied U.S. Natural Gas Exports"

Destination slugs are the lower-cased country name (``south_korea``, ``united_kingdom``).
Confirmed live 2026-10-26; see ``pipelines/eia/CLAUDE.md``.
"""

from __future__ import annotations

import re

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

ROUTE = "natural-gas/move/expc"
TOTAL_SERIES = "N9133US2"
# EIA names the same kind of series several ways ("Liquefied U.S. Natural Gas ..." and
# "U.S. Liquefied Natural Gas ...", "Vessel" and "Vessels"), all confirmed live.
# ...and the unit itself two ways: "(Million Cubic Feet)" and, for the UK, Italy and
# Turkiye among others, "(MMcf)". Missing the second drops 10-20% of US exports.
_VOLUME = r" \((?:Million Cubic Feet|MMcf)\)"
_PATTERNS = (
    (re.compile(r"Liquefied (?:U\.S\. )?Natural Gas Exports by Vessels?\s+to (.+?)" + _VOLUME),
     "exports"),
    (re.compile(r"Liquefied (?:U\.S\. )?Natural Gas Re-Exports to (.+?)" + _VOLUME), "reexports"),
    (re.compile(r"Liquefied (?:U\.S\. )?Natural Gas Exports by Truck to (.+?)" + _VOLUME), "truck"),
)  # fmt: skip


def slug(country: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", country.lower()).strip("_")


def lng_series(facets: list[dict[str, str]]) -> dict[str, str]:
    """``{EIA series code: lake series id}`` for every LNG export and re-export series by
    destination, plus the national total. Price series (``$/Mcf``) never match."""
    out = {TOTAL_SERIES: "eia.lng.exports.total"}
    for facet in facets:
        name = facet.get("name", "")
        for pattern, kind in _PATTERNS:
            match = pattern.search(name)
            if match:
                out[facet["id"]] = f"eia.lng.{kind}.{slug(match.group(1))}"
    return out


@fails_loudly("eia lng exports")
def main() -> None:
    client = EIAClient()
    try:
        ids = lng_series(client.list_series(ROUTE))
        rows = client.get_series(ROUTE, list(ids), "monthly", geo_map=dict.fromkeys(ids, "US"))
    except (requests.RequestException, KeyError, ValueError) as exc:
        record_failure("eia lng exports", exc)
        return
    if rows.empty:
        record_failure("eia lng exports", RuntimeError("no rows"))
        return
    rows = rows.assign(series_id=rows["series_id"].map(ids), freq="M")
    write_ts_long(pd.DataFrame(rows), source="eia")
    destinations = rows.loc[rows["series_id"].str.startswith("eia.lng.exports."), "series_id"]
    print(
        f"eia lng exports: wrote {len(rows)} rows, {destinations.nunique() - 1} destinations, "
        f"{rows['ts'].min():%Y-%m} to {rows['ts'].max():%Y-%m}",
        flush=True,
    )


if __name__ == "__main__":
    main()
