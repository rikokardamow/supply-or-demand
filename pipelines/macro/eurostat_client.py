"""Eurostat JSON-stat 2.0 client for the Economic Sentiment Indicator (ESI).

Confirmed live: dataset `ei_bssi_m_r2`, `indic=BS-ESI-I` ("Economic sentiment
indicator"), `s_adj=SA` (seasonally adjusted). Geo codes are **not** what a naive
guess would produce -- confirmed live: bare `EU`/`EA`/`EA19` all return a genuinely
empty geo dimension (zero categories, zero values, no error) rather than failing
loudly. The real current codes are `EU27_2020` (not `EU`) and `EA20` (not `EA`/
`EA19`) -- Eurostat's own area definitions have been updated over time. Country codes
(`DE`/`FR`/`IT`/`ES`/`IE`) work directly as ISO2, no translation needed."""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bssi_m_r2"
REQUEST_TIMEOUT_SECONDS = 30

# This project's own short geo code -> Eurostat's real current wire code.
GEO_CODES: dict[str, str] = {
    "EU": "EU27_2020",
    "DE": "DE",
    "FR": "FR",
    "IT": "IT",
    "ES": "ES",
    "IE": "IE",
}


class EurostatESIClient:
    def get_esi(self, geos: list[str] | None = None) -> pd.DataFrame:
        """Returns columns: ts, geo, value -- `geo` uses this project's own short
        codes (EU/DE/FR/IT/ES/IE), not Eurostat's own wire codes (e.g. EU27_2020)."""
        geos = geos if geos is not None else list(GEO_CODES)
        wire_codes = [GEO_CODES[g] for g in geos]
        params = {
            "format": "JSON",
            "lang": "en",
            "indic": "BS-ESI-I",
            "s_adj": "SA",
            "geo": wire_codes,
        }
        response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        return _parse_json_stat(payload)


def _parse_json_stat(payload: dict[str, Any]) -> pd.DataFrame:
    """JSON-stat 2.0's `value` is a flat dict keyed by a row-major-flattened index
    string across every dimension in `payload["id"]` order. This dataset's own query
    always fixes freq/indic/s_adj to a single category each (size 1), so the only two
    dimensions that actually vary are geo and time -- confirmed live: flat_index =
    geo_position * len(time) + time_position. A time label like "2026-08" parses
    directly via pd.Timestamp (no need to append "-01")."""
    geo_dim = payload["dimension"]["geo"]["category"]["index"]
    time_dim = payload["dimension"]["time"]["category"]["index"]
    time_size = len(time_dim)
    wire_to_short = {wire: short for short, wire in GEO_CODES.items()}

    values = payload["value"]
    rows = []
    for wire_code, geo_pos in geo_dim.items():
        short_geo = wire_to_short.get(wire_code)
        if short_geo is None:
            continue  # a geo Eurostat returned that this project doesn't track
        for time_label, time_pos in time_dim.items():
            flat_index = geo_pos * time_size + time_pos
            value = values.get(str(flat_index))
            if value is None:
                continue  # a real gap in Eurostat's own data for this geo/month
            rows.append({"ts": pd.Timestamp(time_label), "geo": short_geo, "value": value})

    return pd.DataFrame(rows, columns=["ts", "geo", "value"])
