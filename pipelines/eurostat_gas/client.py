"""Eurostat JSON-stat 2.0 client for the monthly natural gas datasets.

Keyless. Three datasets, all confirmed live 2026-10-26 (see this package's NOTES.md):

- ``nrg_cb_gasm``: gas supply, transformation and consumption (the monthly balance).
- ``nrg_ti_gasm``: imports by partner country.
- ``nrg_te_gasm``: exports by partner country.

The EU aggregate's geo code is ``EU27_2020``. A bare ``EU`` returns an empty
dimension with no error (`pipelines/macro/NOTES.md` records the same trap for ESI).
"""

from __future__ import annotations

import itertools
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
REQUEST_TIMEOUT_SECONDS = 120
EU_GEO = "EU27_2020"
# Eurostat's codes; Greece is EL, not GR.
MEMBER_GEOS = (
    "AT",
    "BE",
    "BG",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "EL",
    "ES",
    "FI",
    "FR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
)

BALANCE = "nrg_cb_gasm"
IMPORTS = "nrg_ti_gasm"
EXPORTS = "nrg_te_gasm"


def parse_json_stat(payload: dict[str, Any]) -> pd.DataFrame:
    """Any JSON-stat 2.0 dataset -> one row per published cell.

    ``value`` is a dict keyed by the row-major flat index across ``payload["id"]``, in that
    order. A key that is absent is a cell Eurostat does not publish. It is skipped, never
    filled with zero. Returns one column per dimension (codes, not labels) plus ``value``.
    """
    ids: list[str] = payload["id"]
    codes = {dim: list(payload["dimension"][dim]["category"]["index"]) for dim in ids}
    if any(len(c) == 0 for c in codes.values()):
        return pd.DataFrame(columns=[*ids, "value"])
    values: dict[str, float] = payload["value"]
    rows = []
    for flat, combo in enumerate(itertools.product(*(codes[dim] for dim in ids))):
        value = values.get(str(flat))
        if value is not None:
            rows.append((*combo, float(value)))
    return pd.DataFrame(rows, columns=[*ids, "value"])


class EurostatGasClient:
    def fetch(self, dataset: str, **filters: str | list[str]) -> pd.DataFrame:
        """One dataset, filtered; the EU-27 aggregate unless ``geo`` is given.

        Raises on an HTTP error, on an error payload, and on a dimension with no categories,
        which is how Eurostat answers an unknown filter code.
        """
        params: dict[str, str | list[str]] = {
            "format": "JSON",
            "lang": "EN",
            "geo": EU_GEO,
            **filters,
        }
        response = requests.get(BASE_URL + dataset, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if "id" not in payload:
            raise ValueError(f"eurostat {dataset}: no dataset in response: {payload!r:.200}")
        empty = [d for d in payload["id"] if not payload["dimension"][d]["category"]["index"]]
        if empty:
            # A filter value Eurostat does not know comes back 200 with that dimension empty
            # (confirmed live: siec=NOT_A_CODE). It is a wrong request, not "no data".
            raise ValueError(f"eurostat {dataset}: no categories for {empty}; check {filters}")
        return parse_json_stat(payload)

    def balance(self, unit: str, **filters: str | list[str]) -> pd.DataFrame:
        return self.fetch(BALANCE, siec="G3000", unit=unit, **filters)

    def trade(self, dataset: str, **filters: str | list[str]) -> pd.DataFrame:
        """Imports or exports by partner, both natural gas (G3000) and LNG (G3200)."""
        return self.fetch(dataset, unit="MIO_M3", **filters)
