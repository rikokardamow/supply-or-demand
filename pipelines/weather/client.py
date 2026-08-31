"""Open-Meteo forecast + archive client. No API key needed -- free, non-commercial.
Confirmed live during planning (see NOTES.md): both endpoints share an identical response
shape; a batched multi-city request (comma-separated lat/lon) returns a JSON array of
per-location objects in the same order as the input; the real wind param name is
`wind_speed_10m_max` (the spec text names the stale `windspeed_10m_max`)."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import pandas as pd
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MAX_RETRIES = 5
BACKOFF_CAP_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 45
RATE_LIMIT_WAIT_SECONDS = 65.0
# Courtesy pacing between successive multi-year archive calls for different city groups
# (EU then US) -- confirmed live that two such "expensive" calls issued back to back
# reliably trip Open-Meteo's per-minute quota even after a RATE_LIMIT_WAIT_SECONDS
# reactive retry-wait, so callers pace proactively instead of relying on retries alone.
GROUP_PACING_SECONDS = 65.0

DAILY_VARS = "temperature_2m_mean,temperature_2m_min,temperature_2m_max,wind_speed_10m_max"


def _get(base_url: str, params: dict[str, Any]) -> Any:
    """Mirrors pipelines/gie/client.py's _get retry/backoff pattern for network errors
    and 5xx (exponential, capped at 60s). 429 is handled differently -- confirmed live
    that Open-Meteo's free tier enforces a *per-minute* quota ("Minutely API request
    limit exceeded. Please try again in one minute.") that a multi-year, multi-city
    archive request can exhaust on its own, so a short exponential backoff from 1s
    never actually clears it within the retry budget; a fixed ~65s wait does."""
    backoff = 1.0
    for attempt in range(MAX_RETRIES):
        last_attempt = attempt == MAX_RETRIES - 1
        try:
            response = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException:
            if last_attempt:
                raise
            time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
            backoff *= 2
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429 and not last_attempt:
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
            continue

        retryable = response.status_code >= 500
        if retryable and not last_attempt:
            time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
            backoff *= 2
            continue
        response.raise_for_status()

    raise RuntimeError("unreachable")


def _parse_daily_response(raw: Any, cities: pd.DataFrame) -> pd.DataFrame:
    """`raw` is Open-Meteo's own response body -- a list of per-location dicts for a
    batched (>1 city) request, confirmed live to preserve input order, or a single dict
    for exactly one city. Both shapes normalise to the same long frame here."""
    locations = raw if isinstance(raw, list) else [raw]
    if len(locations) != len(cities):
        raise ValueError(
            f"Expected {len(cities)} locations back from Open-Meteo, got {len(locations)}"
        )

    frames = []
    for city_row, location in zip(cities.itertuples(), locations, strict=True):
        daily = location["daily"]
        frames.append(
            pd.DataFrame(
                {
                    "city": city_row.city,
                    "ts": pd.to_datetime(daily["time"]),
                    "temp_mean_c": daily["temperature_2m_mean"],
                    "temp_min_c": daily.get("temperature_2m_min"),
                    "temp_max_c": daily.get("temperature_2m_max"),
                    "wind_max_kmh": daily.get("wind_speed_10m_max"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _batched_request(url: str, cities: pd.DataFrame, extra_params: dict[str, Any]) -> pd.DataFrame:
    params = {
        "latitude": ",".join(cities["lat"].astype(str)),
        "longitude": ",".join(cities["lon"].astype(str)),
        "daily": DAILY_VARS,
        "timezone": "auto",
        **extra_params,
    }
    raw = _get(url, params)
    return _parse_daily_response(raw, cities)


def fetch_forecast(cities: pd.DataFrame, days: int = 16) -> pd.DataFrame:
    """One batched request for every city in `cities` (call once per base-group -- EU
    cities together, US cities together -- so a single response's row order lines up 1:1
    with the input frame)."""
    return _batched_request(FORECAST_URL, cities, {"forecast_days": days})


def fetch_archive(cities: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return _batched_request(
        ARCHIVE_URL, cities, {"start_date": start.isoformat(), "end_date": end.isoformat()}
    )
