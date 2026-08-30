"""ENTSO-E Transparency Platform client — thin wrapper around entsoe-py's
EntsoePandasClient. Gotchas documented in pipelines/entsoe/CLAUDE.md.

Never print a raw exception from this client (or entsoe-py itself) — ENTSO-E authenticates
via a securityToken *query parameter*, and requests.HTTPError's default string embeds the
full request URL. Confirmed live (2026-08-30): printing str(exc) for debugging leaked the
real API key into a chat transcript. Every error path here converts to a RuntimeError with
only the HTTP status code, never the original exception or its message."""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests
from core.settings import settings
from entsoe.entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError

MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0

# entsoe-py's own @retry decorator only catches connection-level errors (ConnectionError,
# DNS failures, RemoteDisconnected) — confirmed by reading entsoe.decorators.retry's source.
# It does NOT retry on HTTP error status codes, so a confirmed-live 503 (the Transparency
# Platform is genuinely flaky — the identical query returned 200 once and 503 minutes later
# during planning) propagates immediately as requests.exceptions.HTTPError. This client adds
# its own status-code retry on top, same pattern as pipelines/eia and pipelines/gie.


class ENTSOEClient:
    def __init__(self) -> None:
        self._client = EntsoePandasClient(api_key=settings.entsoe_api_key)

    def get_day_ahead_prices(self, zone: str, start: date, end: date) -> pd.DataFrame:
        """Day-ahead prices for one zone, EUR/MWh. Returns columns ["ts", "value",
        "freq"] — ts is naive UTC (entsoe-py returns a tz-aware, zone-local index);
        freq is inferred from the actual spacing between points, since resolution
        varies by zone (confirmed live: DE_LU is 15-minute, not hourly — don't assume
        one resolution for every zone, per the spec's own freq='H' or '15T' note)."""
        start_ts = pd.Timestamp(start, tz="Europe/Brussels")
        end_ts = pd.Timestamp(end, tz="Europe/Brussels")

        series = self._request_with_retry(zone, start_ts, end_ts)
        if series.empty:
            return pd.DataFrame(columns=["ts", "value", "freq"])

        index = pd.DatetimeIndex(series.index)
        ts = index.tz_convert("UTC").tz_localize(None)
        freq = _infer_freq(index)
        return pd.DataFrame({"ts": ts, "value": series.to_numpy(), "freq": freq})

    def _request_with_retry(
        self, zone: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp
    ) -> pd.Series:
        backoff = 1.0
        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                result: pd.Series = self._client.query_day_ahead_prices(
                    zone, start=start_ts, end=end_ts
                )
                return result
            except NoMatchingDataError:
                return pd.Series(dtype=float)
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                retryable = status is not None and (status == 503 or status >= 500)
                if retryable and not last_attempt:
                    time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                    backoff *= 2
                    continue
                raise RuntimeError(f"ENTSO-E request failed with HTTP {status}") from None

        raise RuntimeError("unreachable")


def _infer_freq(index: pd.DatetimeIndex) -> str:
    if len(index) < 2:
        return "H"
    delta = index[1] - index[0]
    return "15T" if delta <= pd.Timedelta(minutes=15) else "H"
