"""EIA API v2 client. Route/facet pattern documented in pipelines/eia/NOTES.md."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests
from core.settings import settings

BASE_URL = "https://api.eia.gov/v2"
PAGE_SIZE = 5000


class EIAClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.eia_api_key

    def get_series(self, route: str, series: list[str], frequency: str) -> pd.DataFrame:
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

        pulled_at = datetime.now(UTC)
        return pd.DataFrame(
            {
                "series_id": [row["series"] for row in rows],
                "source": "eia",
                "ts": pd.to_datetime([row["period"] for row in rows]),
                "value": [float(row["value"]) for row in rows],
                "unit": [row["units"] for row in rows],
                "geo": [row.get("area", "") for row in rows],
                "freq": frequency,
                "revision_date": pulled_at,
            }
        )
