"""GIE AGSI+/ALSI+ API client. Auth/pagination pattern documented in pipelines/gie/CLAUDE.md."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests
from core.settings import settings

AGSI_BASE_URL = "https://agsi.gie.eu/api"
ALSI_BASE_URL = "https://alsi.gie.eu/api"
MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0
PAGE_PACING_SECONDS = 0.3
DATE_PACING_SECONDS = 0.15

TS_LONG_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]

# (ts_long series_id suffix, unit, row -> raw value)
FieldSpec = tuple[str, str, Callable[[dict[str, Any]], Any]]

AGSI_FIELDS: list[FieldSpec] = [
    ("full_pct", "%", lambda r: r.get("full")),
    ("gas_in_storage", "TWh", lambda r: r.get("gasInStorage")),
    ("injection", "GWh/d", lambda r: r.get("injection")),
    ("withdrawal", "GWh/d", lambda r: r.get("withdrawal")),
    ("working_gas_volume", "TWh", lambda r: r.get("workingGasVolume")),
]

# inventory/dtmi are nested {"lng": <1000 m3>, "gwh": <energy equivalent>} — .lng matches
# the spec's "lngInventory" naming (a volume, not an energy figure). Confirmed against
# alsi.gie.eu's own published units ("103 m3 LNG").
ALSI_FIELDS: list[FieldSpec] = [
    ("lng_inventory", "1000 m3", lambda r: (r.get("inventory") or {}).get("lng")),
    ("send_out", "GWh/d", lambda r: r.get("sendOut")),
    ("dtmi", "1000 m3", lambda r: (r.get("dtmi") or {}).get("lng")),
]


def _is_missing(value: Any) -> bool:
    return value is None or value == "-"


class GIEClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.gie_api_key

    def _get(self, base_url: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"x-key": self._api_key}
        backoff = 1.0

        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                response = requests.get(base_url, headers=headers, params=params, timeout=45)
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
        """Single-country history via the main /api endpoint (from/to + page pagination,
        30 rows/page). Still useful for a one-off country pull; get_agsi_eu_tree_history
        covers EU + every member country in one pass and is what pull_agsi.py uses."""
        records: list[dict[str, Any]] = []
        page = 1

        while True:
            body = self._get(
                AGSI_BASE_URL,
                {
                    "country": country,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "page": page,
                },
            )
            for row in body.get("data", []):
                records.extend(_row_records(row, "agsi", country.upper(), AGSI_FIELDS))
            last_page = body.get("last_page", 1)
            if page >= last_page:
                break
            page += 1
            time.sleep(PAGE_PACING_SECONDS)

        return _records_to_ts_long(records)

    def get_agsi_eu_tree_history(self, start: date, end: date) -> pd.DataFrame:
        return self._get_eu_tree_history(AGSI_BASE_URL, "agsi", AGSI_FIELDS, start, end)

    def get_alsi_eu_tree_history(self, start: date, end: date) -> pd.DataFrame:
        return self._get_eu_tree_history(ALSI_BASE_URL, "alsi", ALSI_FIELDS, start, end)

    def _get_eu_tree_history(
        self,
        base_url: str,
        prefix: str,
        fields: list[FieldSpec],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """`/api/eu` only accepts a single `date` param (no from/to + page) — loop one day
        at a time. Each response's "eu" row nests every member country's own data under
        "children"; extract the EU aggregate plus each 2-letter-code child country
        (skips deeper facility-level nesting and non-EU "ne" row entirely)."""
        records: list[dict[str, Any]] = []
        current = start
        total_days = (end - start).days + 1
        processed = 0
        started_at = time.monotonic()
        log_every = max(1, total_days // 20)  # ~20 progress lines across the whole pull

        while current <= end:
            body = self._get(f"{base_url}/eu", {"date": current.isoformat()})
            eu_row = next((r for r in body.get("data", []) if r.get("code") == "eu"), None)
            if eu_row is not None:
                records.extend(_row_records(eu_row, prefix, "EU", fields))
                for child in eu_row.get("children", []):
                    code = child.get("code")
                    if code and len(code) == 2:
                        records.extend(_row_records(child, prefix, code.upper(), fields))
            current += timedelta(days=1)
            processed += 1

            if processed % log_every == 0 or processed == total_days:
                # time.monotonic() excludes OS-suspend time, unlike wall-clock timestamps —
                # avoids a misleading ETA if the machine sleeps mid-pull.
                elapsed = time.monotonic() - started_at
                remaining = (elapsed / processed) * (total_days - processed)
                print(
                    f"[{prefix}] {processed}/{total_days} days "
                    f"({processed / total_days:.0%}) — elapsed {elapsed / 60:.1f}m, "
                    f"est. remaining {remaining / 60:.1f}m",
                    flush=True,
                )

            time.sleep(DATE_PACING_SECONDS)

        return _records_to_ts_long(records)


def _row_records(
    row: dict[str, Any], prefix: str, geo: str, fields: list[FieldSpec]
) -> list[dict[str, Any]]:
    ts = row.get("gasDayStart")
    updated_at = row.get("updatedAt")
    if ts is None or updated_at is None:
        return []

    records = []
    for series_suffix, unit, extractor in fields:
        value = extractor(row)
        if _is_missing(value):
            continue
        records.append(
            {
                "series_id": f"{prefix}.{geo}.{series_suffix}",
                "source": "gie",
                "ts": ts,
                "value": float(value),
                "unit": unit,
                "geo": geo,
                "freq": "D",
                "revision_date": updated_at,
            }
        )
    return records


def _records_to_ts_long(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=TS_LONG_COLUMNS)
    df = pd.DataFrame(records)
    df["ts"] = pd.to_datetime(df["ts"])
    df["revision_date"] = pd.to_datetime(df["revision_date"])
    return df
