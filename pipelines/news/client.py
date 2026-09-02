"""GDELT DOC 2.0 API client -- free, no key. Gotchas documented in
pipelines/news/CLAUDE.md, most importantly: api.gdeltproject.org is genuinely, severely
flaky (confirmed live -- most calls hang until a long connect-timeout, some reset
instantly, only a fraction succeed quickly), so this client retries patiently rather than
failing fast."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 6
BACKOFF_START_SECONDS = 5.0
BACKOFF_CAP_SECONDS = 60.0

# GDELT's own artlist JSON field names, confirmed live -- not the spec's own generic
# naming. seendate is a compact, non-ISO timestamp: "20260831T233000Z".
SEENDATE_FORMAT = "%Y%m%dT%H%M%SZ"


class GDELTClient:
    def search(
        self, query: str, timespan: str = "7d", maxrecords: int = 250
    ) -> pd.DataFrame:
        """Returns columns: url, title, seendate (parsed to a real Timestamp), domain,
        language, sourcecountry -- GDELT's own artlist fields, confirmed live. Never
        raises on the confirmed-live flakiness until every retry is exhausted."""
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": maxrecords,
            "timespan": timespan,
        }
        payload = self._get(params)
        articles = payload.get("articles", [])
        if not articles:
            return pd.DataFrame(
                columns=["url", "title", "seendate", "domain", "language", "sourcecountry"]
            )

        df = pd.DataFrame(articles)
        df["seendate"] = pd.to_datetime(df["seendate"], format=SEENDATE_FORMAT)
        return df[["url", "title", "seendate", "domain", "language", "sourcecountry"]]

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        backoff = BACKOFF_START_SECONDS
        for attempt in range(MAX_RETRIES):
            last_attempt = attempt == MAX_RETRIES - 1
            try:
                response = requests.get(
                    BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
            except (requests.exceptions.RequestException, ValueError):
                # Three distinct failure modes confirmed live, all retried the same
                # way: a connect-timeout (the endpoint hangs), an instant connection
                # reset, and -- caught while recording this pipeline's own test
                # cassette -- a genuine HTTP 200 whose body is a plain-text rate-limit
                # notice ("Please limit requests to one every 5 seconds..."), not
                # JSON. response.json() raises requests.exceptions.JSONDecodeError on
                # that body, which happens to subclass RequestException in the
                # installed requests version -- but ValueError is caught explicitly
                # here too so this stays correct regardless of that implementation
                # detail (json.JSONDecodeError, the stdlib's own, is a ValueError).
                if last_attempt:
                    raise
                time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                backoff *= 2

        raise RuntimeError("unreachable")
