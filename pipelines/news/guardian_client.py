"""The Guardian Open Platform client -- free key required (`settings.guardian_key`),
production-safe per the spec (unlike GDELT, not documented or observed as flaky).
Exposes the same `.search(query, ...) -> pd.DataFrame` shape as `client.py::GDELTClient`
(columns: url, title, seendate, domain, language, sourcecountry) so `pull_news.py` can
loop over both sources uniformly.

**Live verification is pending a real key** (`GUARDIAN_KEY` in .env is empty as of
writing) -- built against Guardian's own public, versioned API reference
(https://open-platform.theguardian.com/documentation/) rather than a live-confirmed
response, unlike every other client in this codebase. See NOTES.md for what still
needs confirming once a real key is available: the exact field names below, and
whether `content-type=article` or similar filtering is worth adding."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests
from core.failures import raise_sanitised
from core.settings import settings

BASE_URL = "https://content.guardianapis.com/search"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
BACKOFF_START_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 30.0

# Guardian is a single, known outlet -- these two fields carry no real per-article
# information the way GDELT's domain/language do, but are filled in for column-shape
# parity with GDELTClient.search's output.
DOMAIN = "theguardian.com"
LANGUAGE = "English"
# The *publisher's* country, same caveat as GDELT's own sourcecountry field (see
# pipelines/news/tagging.py) -- a fallback only, overridden by any headline-derived
# geo keyword.
PUBLISHER_COUNTRY = "United Kingdom"


class GuardianClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.guardian_key

    def search(self, query: str, page_size: int = 50) -> pd.DataFrame:
        """Returns columns: url, title, seendate, domain, language, sourcecountry --
        matching GDELTClient.search's own shape."""
        params = {
            "q": query,
            "api-key": self._api_key,
            "page-size": page_size,
            "order-by": "newest",
        }
        payload = self._get(params)
        results = payload.get("response", {}).get("results", [])
        if not results:
            return pd.DataFrame(
                columns=["url", "title", "seendate", "domain", "language", "sourcecountry"]
            )

        df = pd.DataFrame(results)
        return pd.DataFrame(
            {
                "url": df["webUrl"],
                "title": df["webTitle"],
                "seendate": pd.to_datetime(df["webPublicationDate"]),
                "domain": DOMAIN,
                "language": LANGUAGE,
                "sourcecountry": PUBLISHER_COUNTRY,
            }
        )

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
            except (requests.exceptions.RequestException, ValueError) as exc:
                if last_attempt:
                    # `api-key` is a query parameter, so a raw HTTPError carries the real
                    # key in its message (golden rule 1). Retries still see the original
                    # exception above -- only what escapes this loop is sanitised.
                    raise_sanitised(exc)
                time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                backoff *= 2

        raise RuntimeError("unreachable")
