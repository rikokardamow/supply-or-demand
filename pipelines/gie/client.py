"""GIE AGSI+ API client. Auth/pagination pattern documented in pipelines/gie/NOTES.md."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import pandas as pd
import requests
from core.settings import settings

BASE_URL = "https://agsi.gie.eu/api"
MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0
PAGE_PACING_SECONDS = 0.3

# EIA-API-field -> (ts_long series_id suffix, unit)
FIELD_MAP: dict[str, tuple[str, str]] = {
    "full": ("full_pct", "%"),
    "gasInStorage": ("gas_in_storage", "TWh"),
    "injection": ("injection", "GWh/d"),
    "withdrawal": ("withdrawal", "GWh/d"),
    "workingGasVolume": ("working_gas_volume", "TWh"),
}


class GIEClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.gie_api_key

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"x-key": self._api_key}
        backoff = 1.0

        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                response = requests.get(BASE_URL, headers=headers, params=params, timeout=45)
            except requests.exceptions.RequestException:
                if last_attempt:
                    raise
                time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                backoff *= 2
                continue

            if response.status_code == 200:
                body: dict[str, Any] = response.json()
                return body

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and not last_attempt:
                time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                backoff *= 2
                continue
            response.raise_for_status()

        raise RuntimeError("unreachable")

    def get_agsi_history(self, country: str, start: date, end: date) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        page = 1

        while True:
            body = self._get(
                {
                    "country": country,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "page": page,
                }
            )
            rows.extend(body.get("data", []))
            last_page = body.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(PAGE_PACING_SECONDS)

        return _rows_to_ts_long(rows, country)


def _rows_to_ts_long(rows: list[dict[str, Any]], country: str) -> pd.DataFrame:
    geo = country.upper()
    frames = []
    for api_field, (series_suffix, unit) in FIELD_MAP.items():
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"agsi.{geo}.{series_suffix}",
                    "source": "gie",
                    "ts": pd.to_datetime([row["gasDayStart"] for row in rows]),
                    "value": [float(row[api_field]) for row in rows],
                    "unit": unit,
                    "geo": geo,
                    "freq": "D",
                    "revision_date": pd.to_datetime([row["updatedAt"] for row in rows]),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
