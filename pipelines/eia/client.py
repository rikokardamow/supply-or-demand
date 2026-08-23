"""EIA API v2 client. Route/facet pattern documented in pipelines/eia/CLAUDE.md."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests
from core.settings import settings

BASE_URL = "https://api.eia.gov/v2"
PAGE_SIZE = 5000


def _normalise_geo(area_name: str) -> str:
    if area_name == "U.S.":
        return "US"
    if area_name.startswith("PADD "):
        return "PADD" + area_name.removeprefix("PADD ")
    return area_name


class EIAClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.eia_api_key

    def _fetch_rows(self, route: str, series: list[str], frequency: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            params: dict[str, Any] = {
                "api_key": self._api_key,
                "frequency": frequency,
                "data[0]": "value",
                "facets[series][]": series,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": offset,
                "length": PAGE_SIZE,
            }
            response = requests.get(f"{BASE_URL}/{route}/data/", params=params, timeout=30)
            response.raise_for_status()
            page = response.json()["response"]["data"]
            rows.extend(page)

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return rows

    def list_series(self, route: str) -> list[dict[str, str]]:
        """List every series id/name available under a route, via its facet endpoint.
        Use this to discover series codes instead of guessing them."""
        params = {"api_key": self._api_key}
        response = requests.get(f"{BASE_URL}/{route}/facet/series", params=params, timeout=30)
        response.raise_for_status()
        result: list[dict[str, str]] = response.json()["response"]["facets"]
        return result

    def get_series(self, route: str, series: list[str], frequency: str) -> pd.DataFrame:
        rows = self._fetch_rows(route, series, frequency)
        pulled_at = datetime.now(UTC)
        return pd.DataFrame(
            {
                "series_id": [row["series"] for row in rows],
                "source": "eia",
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "value": [float(row["value"]) for row in rows],
                "unit": [row["units"] for row in rows],
                "geo": [_normalise_geo(row.get("area-name", "")) for row in rows],
                "freq": frequency,
                "revision_date": pulled_at,
            }
        )

    def get_flows(
        self,
        route: str,
        corridors: dict[str, tuple[str, str, str]],
        frequency: str,
    ) -> pd.DataFrame:
        """Like get_series, but returns `flows`-schema rows. `corridors` maps each
        series id to (from_node, to_node, mode)."""
        rows = self._fetch_rows(route, list(corridors), frequency)
        return pd.DataFrame(
            {
                "source": "eia",
                "from_node": [corridors[row["series"]][0] for row in rows],
                "to_node": [corridors[row["series"]][1] for row in rows],
                "value": [float(row["value"]) for row in rows],
                "unit": [row["units"] for row in rows],
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "mode": [corridors[row["series"]][2] for row in rows],
            }
        )
