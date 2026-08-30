"""EirGrid Smart Grid Dashboard client — public, undocumented JSON API, no key.
Gotchas documented in pipelines/eirgrid/NOTES.md. Per the spec's own instruction, every
call goes through one adapter function (_fetch_rows) so a response-shape change breaks
exactly one place."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://www.smartgriddashboard.com/DashboardService.svc/data"
MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0
DATE_FORMAT = "%d-%b-%Y %H:%M"

# Confirmed live: the API is genuinely fragile (503s on a fair share of calls, clears on
# retry) — matches the spec's own "treat as fragile: cache aggressively, be gentle"
# instruction. A courtesy pause between calls, same idea as pipelines/gie's pacing delay.
PACING_SECONDS = 1.0

# Confirmed live: a >30-day range returns a real (non-503) error, "An error has occured
# during the call to the dashboard, please try again" — a genuine server-side range
# limit, not flakiness (a 30-day request for the same area succeeded immediately after).
# get_series chunks any wider request into <=30-day windows transparently.
MAX_RANGE_DAYS = 30


class EirGridClient:
    def get_series(
        self, area: str, region: str, start: date, end: date
    ) -> pd.DataFrame:
        """One (area, region) pull, returned as columns ["ts", "field_name", "value"] —
        `field_name` is EirGrid's own FieldName (e.g. "SYSTEM_DEMAND"), kept raw rather
        than mapped here, since some areas (interconnection) return more than one field
        per row and the pull script decides how to split them into series_ids."""
        rows: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any]] = set()
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=MAX_RANGE_DAYS), end)
            # Each chunk's range is inclusive on both ends (confirmed live), so
            # consecutive chunks would both return the boundary timestamp — dedup by
            # (EffectiveTime, FieldName) rather than relying on write_ts_long's
            # storage-level dedup alone, since callers may use this DataFrame directly.
            for row in self._fetch_rows(area, region, chunk_start, chunk_end):
                key = (row.get("EffectiveTime"), row.get("FieldName"))
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
            chunk_start = chunk_end
        if not rows:
            return pd.DataFrame(columns=["ts", "field_name", "value"])

        # Future/not-yet-occurred timestamps within the requested window come back with
        # value=null (confirmed live, e.g. querying "today" through 23:59) — drop them
        # rather than crash on float(None).
        rows = [r for r in rows if r.get("Value") is not None]
        if not rows:
            return pd.DataFrame(columns=["ts", "field_name", "value"])

        # EffectiveTime is Ireland local time, not UTC (confirmed live: LastUpdated was
        # exactly 1h ahead of datetime.now(UTC) during BST) — localize then convert.
        naive = pd.to_datetime([r["EffectiveTime"] for r in rows], format="%d-%b-%Y %H:%M:%S")
        ts = naive.tz_localize("Europe/Dublin", ambiguous="NaT", nonexistent="NaT")
        ts = ts.tz_convert("UTC").tz_localize(None)

        return pd.DataFrame(
            {
                "ts": ts,
                "field_name": [r["FieldName"] for r in rows],
                "value": [float(r["Value"]) for r in rows],
            }
        )

    def _fetch_rows(
        self, area: str, region: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        params = {
            "area": area,
            "region": region,
            "datefrom": start.strftime(DATE_FORMAT),
            "dateto": end.strftime(DATE_FORMAT),
        }

        backoff = 1.0
        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            time.sleep(PACING_SECONDS)
            try:
                response = requests.get(BASE_URL, params=params, timeout=30)
                response.raise_for_status()
                body = response.json()
            except (requests.exceptions.RequestException, ValueError):
                # ValueError covers JSONDecodeError — a 503 here returns an HTML error
                # page, not JSON, confirmed live.
                if not last_attempt:
                    time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                    backoff *= 2
                    continue
                raise RuntimeError(f"EirGrid request failed for area={area!r}") from None
            else:
                if body.get("ErrorMessage"):
                    raise ValueError(f"EirGrid error for area={area!r}: {body['ErrorMessage']}")
                rows: list[dict[str, Any]] = body.get("Rows", [])
                return rows

        raise RuntimeError("unreachable")
