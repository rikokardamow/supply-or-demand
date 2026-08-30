"""ENTSOG Transparency Platform client — public API, no auth. Endpoint/pagination pattern
documented in pipelines/entsog/NOTES.md."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://transparency.entsog.eu/api/v1"
MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0


class ENTSOGClient:
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        backoff = 1.0
        url = f"{BASE_URL}/{path}"

        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                response = requests.get(url, params=params, timeout=45)
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

    def get_operator_point_directions(self) -> pd.DataFrame:
        """Full point/operator/direction directory — reference data, not a time series,
        so kept as the API's own raw columns rather than reshaped to a lake schema.
        `limit=-1` returns everything in one call (confirmed live: 2,253 rows) — the
        default 100-row page applies an opaque internal filter, don't rely on it."""
        body = self._get("operatorpointdirections.json", {"limit": -1})
        return pd.DataFrame(body["operatorpointdirections"])

    def get_physical_flow(
        self,
        point_key: str,
        direction_key: str,
        start: date,
        end: date,
        operator_key: str | None = None,
    ) -> pd.DataFrame:
        """Raw physical-flow rows for one point+direction, value in kWh/d (unconverted —
        corridor assembly + kWh->GWh conversion happens in the pull scripts using
        corridors.py's mapping, same client/pull split as pipelines/eia).

        Some points are registered to more than one operator (both sides of a
        cross-border point, or a terminal operator alongside the national TSO) — pass
        `operator_key` to disambiguate when corridors.py's PointSpec carries one;
        confirmed live for ITP-00304 (VIP Pirineos), where Enagas and Terega both report
        real, different "entry" values for the same point+direction and would otherwise
        double-count."""
        return self._get_indicator_data(
            "Physical Flow", point_key, direction_key, start, end, operator_key
        )

    def get_nomination(
        self,
        point_key: str,
        direction_key: str,
        start: date,
        end: date,
        operator_key: str | None = None,
    ) -> pd.DataFrame:
        """Raw nomination rows for one point+direction, same shape as get_physical_flow —
        used alongside physical flow for the physical-vs-nomination gap (Session D)."""
        return self._get_indicator_data(
            "Nomination", point_key, direction_key, start, end, operator_key
        )

    def _get_indicator_data(
        self,
        indicator: str,
        point_key: str,
        direction_key: str,
        start: date,
        end: date,
        operator_key: str | None = None,
    ) -> pd.DataFrame:
        params: dict[str, Any] = {
            "indicator": indicator,
            "pointKey": point_key,
            "directionKey": direction_key,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "periodType": "day",
            "limit": -1,
        }
        if operator_key is not None:
            params["operatorKey"] = operator_key
        try:
            body = self._get("operationaldata.json", params)
        except requests.exceptions.HTTPError as exc:
            # ENTSOG returns 404 {"message": "No result found"} for a point+direction+
            # range with no data — confirmed live even for a point the directory marks
            # hasData=True (that flag doesn't guarantee data for every indicator). Not
            # every point is actually flowing; treat *this specific message* as empty,
            # not fatal. A different 404 message exists too (requesting >5 years back
            # hits "Data on the TP is archived..." — a real error, not "no data") so
            # match on the message text rather than blanket-swallowing every 404.
            response = exc.response
            message = response.json().get("message", "") if response is not None else ""
            is_empty_result = (
                response is not None
                and response.status_code == 404
                and message == "No result found"
            )
            if is_empty_result:
                return pd.DataFrame(columns=["ts", "value_kwh_d"])
            raise
        rows = body.get("operationaldata", [])
        # Some points return a full row per day with value="" instead of omitting the
        # day or using null — confirmed live (Dunkerque DKB, ITP-00519: every row in a
        # 31-day range was value=""). Drop those rather than crash on float("").
        rows = [r for r in rows if r.get("value") not in (None, "")]
        if not rows:
            return pd.DataFrame(columns=["ts", "value_kwh_d"])

        # periodFrom is the gas-day label at a fixed local time (e.g. "06:00:00+02:00")
        # whose UTC offset shifts across DST — parsing the full ISO string over a
        # multi-year range mixes +01:00/+02:00 and pd.to_datetime rejects that. Only the
        # calendar date is meaningful for a daily series (same plain-date convention as
        # pipelines/eia and pipelines/gie), so take the date substring directly rather
        # than resolving a timezone.
        ts = pd.to_datetime([r["periodFrom"][:10] for r in rows])
        return pd.DataFrame({"ts": ts, "value_kwh_d": [float(r["value"]) for r in rows]})
