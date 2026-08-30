"""ENTSO-E Transparency Platform client — thin wrapper around entsoe-py's
EntsoePandasClient. Gotchas documented in pipelines/entsoe/CLAUDE.md.

Never print a raw exception from this client (or entsoe-py itself) — ENTSO-E authenticates
via a securityToken *query parameter*, and requests.HTTPError's default string embeds the
full request URL. Confirmed live (2026-08-30): printing str(exc) for debugging leaked the
real API key into a chat transcript. Every error path here converts to a RuntimeError with
only the HTTP status code, never the original exception or its message."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date
from typing import TypeVar

import pandas as pd
import requests
from core.settings import settings
from entsoe.entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError

MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 45

# EntsoePandasClient/EntsoeRawClient default timeout=None (confirmed by reading
# EntsoeRawClient.__init__'s source) — passed straight through to requests.get(...,
# timeout=None), meaning NO client-side timeout at all. Hit this live: a pull hung
# indefinitely on one zone with no exception ever raised (so the retry logic below
# never even triggered) until killed by hand. Always pass an explicit timeout.

# entsoe-py's own @retry decorator only catches connection-level errors (ConnectionError,
# DNS failures, RemoteDisconnected) — confirmed by reading entsoe.decorators.retry's source.
# It does NOT retry on HTTP error status codes, so a confirmed-live 503 (the Transparency
# Platform is genuinely flaky — the identical query returned 200 once and 503 minutes later
# during planning) propagates immediately as requests.exceptions.HTTPError. This client adds
# its own status-code retry on top, same pattern as pipelines/eia and pipelines/gie.

T = TypeVar("T")

TZ = "Europe/Brussels"  # any CET/CEST zone works as entsoe-py's query anchor


class ENTSOEClient:
    def __init__(self) -> None:
        self._client = EntsoePandasClient(
            api_key=settings.entsoe_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        )

    def get_day_ahead_prices(self, zone: str, start: date, end: date) -> pd.DataFrame:
        """Day-ahead prices for one zone, EUR/MWh. Returns columns ["ts", "value",
        "freq"] — freq is inferred from the actual spacing between points, since
        resolution varies by zone (confirmed live: DE_LU/FR/NL are 15-minute, IE_SEM is
        hourly — don't assume one resolution for every zone)."""
        start_ts, end_ts = self._window(start, end)
        series = self._call(
            lambda: self._client.query_day_ahead_prices(zone, start=start_ts, end=end_ts)
        )
        if not isinstance(series, pd.Series) or series.empty:
            return pd.DataFrame(columns=["ts", "value", "freq"])

        index = pd.DatetimeIndex(series.index)
        ts = index.tz_convert("UTC").tz_localize(None)
        freq = _infer_freq(index)
        return pd.DataFrame({"ts": ts, "value": series.to_numpy(), "freq": freq})

    def get_load(self, zone: str, start: date, end: date) -> pd.DataFrame:
        """Actual load (demand), MW. Returns columns ["ts", "value", "freq"]."""
        start_ts, end_ts = self._window(start, end)
        df = self._call(lambda: self._client.query_load(zone, start=start_ts, end=end_ts))
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame(columns=["ts", "value", "freq"])

        index = pd.DatetimeIndex(df.index)
        ts = index.tz_convert("UTC").tz_localize(None)
        freq = _infer_freq(index)
        return pd.DataFrame({"ts": ts, "value": df.iloc[:, 0].to_numpy(), "freq": freq})

    def get_wind_and_solar_forecast(self, zone: str, start: date, end: date) -> pd.DataFrame:
        """Day-ahead wind/solar generation forecast, MW, by PSR type (Solar, Wind
        Onshore, Wind Offshore — confirmed live, not every zone has all three; a
        landlocked zone simply won't have an Offshore column). Returns columns ["ts",
        "psr_type", "value", "freq"]."""
        start_ts, end_ts = self._window(start, end)
        df = self._call(
            lambda: self._client.query_wind_and_solar_forecast(zone, start=start_ts, end=end_ts)
        )
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame(columns=["ts", "psr_type", "value", "freq"])

        index = pd.DatetimeIndex(df.index)
        freq = _infer_freq(index)
        ts = index.tz_convert("UTC").tz_localize(None)
        melted = df.set_index(ts).reset_index(names="ts").melt(
            id_vars="ts", var_name="psr_type", value_name="value"
        )
        melted["freq"] = freq
        return melted

    def get_generation(self, zone: str, start: date, end: date) -> pd.DataFrame:
        """Actual generation by PSR type, MW. Returns columns ["ts", "psr_type",
        "value", "freq"]. Only "Actual Aggregated" columns are kept — pumped-storage's
        "Actual Consumption" column (confirmed live present for Hydro Pumped Storage)
        is charging demand, not generation, and doesn't belong in a generation mix."""
        start_ts, end_ts = self._window(start, end)
        df = self._call(lambda: self._client.query_generation(zone, start=start_ts, end=end_ts))
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame(columns=["ts", "psr_type", "value", "freq"])

        if isinstance(df.columns, pd.MultiIndex):
            agg_cols = [c for c in df.columns if c[1] == "Actual Aggregated"]
            df = df[agg_cols]
            df.columns = [c[0] for c in df.columns]

        index = pd.DatetimeIndex(df.index)
        freq = _infer_freq(index)
        ts = index.tz_convert("UTC").tz_localize(None)
        melted = df.set_index(ts).reset_index(names="ts").melt(
            id_vars="ts", var_name="psr_type", value_name="value"
        )
        melted["freq"] = freq
        return melted

    def get_crossborder_flow(
        self, zone_from: str, zone_to: str, start: date, end: date
    ) -> pd.DataFrame:
        """Physical cross-border flow zone_from -> zone_to, MW. Returns columns ["ts",
        "value", "freq"]."""
        start_ts, end_ts = self._window(start, end)
        series = self._call(
            lambda: self._client.query_crossborder_flows(
                zone_from, zone_to, start=start_ts, end=end_ts
            )
        )
        if not isinstance(series, pd.Series) or series.empty:
            return pd.DataFrame(columns=["ts", "value", "freq"])

        index = pd.DatetimeIndex(series.index)
        ts = index.tz_convert("UTC").tz_localize(None)
        freq = _infer_freq(index)
        return pd.DataFrame({"ts": ts, "value": series.to_numpy(), "freq": freq})

    @staticmethod
    def _window(start: date, end: date) -> tuple[pd.Timestamp, pd.Timestamp]:
        return pd.Timestamp(start, tz=TZ), pd.Timestamp(end, tz=TZ)

    def _call(self, fn: Callable[[], T]) -> T | pd.Series:
        backoff = 1.0
        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                return fn()
            except NoMatchingDataError:
                return pd.Series(dtype=float)
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                retryable = status is not None and status >= 500
                if retryable and not last_attempt:
                    time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                    backoff *= 2
                    continue
                raise RuntimeError(f"ENTSO-E request failed with HTTP {status}") from None
            except requests.exceptions.RequestException as exc:
                # Timeouts/connection errors carry no response at all — same backoff
                # treatment, since these are exactly the kind of transient failure the
                # confirmed-live flakiness produces (a hang is the connection-level
                # cousin of a 503, not a reason to give up faster).
                if not last_attempt:
                    time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                    backoff *= 2
                    continue
                raise RuntimeError(f"ENTSO-E request failed: {type(exc).__name__}") from None

        raise RuntimeError("unreachable")


def _infer_freq(index: pd.DatetimeIndex) -> str:
    if len(index) < 2:
        return "H"
    delta = index[1] - index[0]
    return "15T" if delta <= pd.Timedelta(minutes=15) else "H"
