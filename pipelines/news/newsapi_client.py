"""NewsAPI.org client -- free key required (`settings.newsapi_key`). **Manual/
on-demand use only, never a scheduled pull** -- NewsAPI's free Developer tier is
dev/testing only per its own ToS (not licensed for production use, 100 req/day,
24h publish delay), a real constraint Spec 09 already found and deliberately
designed around (see that spec's own Definition of Done: "NewsAPI absent from
scheduled pulls"). See specs/16_newsapi-supplement.md and this package's own
NOTES.md for the full reasoning -- do not wire this client into pull_news.py::main.

Exposes the same `.search(query, ...) -> pd.DataFrame` shape as
`client.py::GDELTClient`/`guardian_client.py::GuardianClient` (columns: url, title,
seendate, domain, language, sourcecountry) so `pipelines/news/events.py::
articles_to_events` needs no changes.

Real `/v2/everything` response shape, confirmed live against a real key (not just
the vendor's own published reference): `{"status": "ok", "totalResults": N,
"articles": [{"source": {"id": ..., "name": ...}, "author": ..., "title": ...,
"description": ..., "url": ..., "urlToImage": ..., "publishedAt":
"2026-09-02T06:15:53Z", "content": ...}]}` -- `publishedAt` is real ISO 8601,
parseable by a bare `pd.to_datetime` with no explicit `format=` (unlike GDELT's
compact `seendate`)."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests
from core.failures import raise_sanitised
from core.settings import settings

BASE_URL = "https://newsapi.org/v2/everything"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
BACKOFF_START_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 30.0

# NewsAPI's /everything endpoint returns neither a per-article language code nor a
# publisher-country field (confirmed live) -- "unknown" language means
# pipelines/news/translate.py::translate_headline correctly no-ops for these rows
# (same behaviour as the ~1000 pre-language-schema GDELT/Guardian rows already in
# the lake) rather than guessing; an empty sourcecountry falls through to geo
# resolving purely via headline keywords, same as every other source.
UNKNOWN_LANGUAGE = "unknown"
UNKNOWN_SOURCECOUNTRY = ""


class NewsAPIClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.newsapi_key

    def search(self, query: str, page_size: int = 100) -> pd.DataFrame:
        """Returns columns: url, title, seendate, domain, language, sourcecountry --
        matching GDELTClient.search's own shape. `language` deliberately left unset
        on the request itself -- setting it would silently exclude non-English
        results before they ever reach the translate pipeline."""
        params = {
            "q": query,
            "pageSize": page_size,
            "sortBy": "publishedAt",
            "apiKey": self._api_key,
        }
        payload = self._get(params)
        articles = payload.get("articles", [])
        if not articles:
            return pd.DataFrame(
                columns=["url", "title", "seendate", "domain", "language", "sourcecountry"]
            )

        df = pd.DataFrame(articles)
        return pd.DataFrame(
            {
                "url": df["url"],
                "title": df["title"],
                "seendate": pd.to_datetime(df["publishedAt"]),
                "domain": df["source"].map(lambda s: s.get("name", "")),
                "language": UNKNOWN_LANGUAGE,
                "sourcecountry": UNKNOWN_SOURCECOUNTRY,
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
                    # `apiKey` is a query parameter, so a raw HTTPError carries the real
                    # key in its message (golden rule 1). Retries still see the original
                    # exception above -- only what escapes this loop is sanitised.
                    raise_sanitised(exc)
                time.sleep(min(backoff, BACKOFF_CAP_SECONDS))
                backoff *= 2

        raise RuntimeError("unreachable")
