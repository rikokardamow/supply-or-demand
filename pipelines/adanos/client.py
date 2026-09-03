"""Adanos Market Sentiment API client (`api.adanos.org`) -- free key required
(`settings.adanos_api_key`, `X-API-Key` header). Confirmed live against a real key
(not just the vendor's own pasted docs): `/compare` and `/trending/sectors` both
match the documented shape exactly.

**Critical, confirmed-live gotcha: `/compare` NEVER returns an error for an
unrecognised ticker.** A deliberately fake ticker (`NOTAREALTICKER123`) still
returns HTTP 200 with a zeroed row -- `company_name: null`, `buzz_score: 0.0`,
`sentiment_score: null` -- identical in shape to a genuinely-supported ticker that
simply has no qualifying data this period (confirmed live: `GENL`/`GKP`/`OANDO`/
`ARADEL` all return real `company_name` values but zeroed metrics, since Reddit
retail attention on LSE/NGX-listed frontier producers is genuinely near zero).
**The only real existence signal is a non-null `company_name`** -- "the call
succeeded" is not evidence a ticker is real. See `pipelines/adanos/tickers.py` for
where this caught one real wrong guess (`SEPL` vs the real `SEPLAT`).

All four platform `/compare` endpoints (reddit/x/news/polymarket) share the same
core fields this project actually uses -- `ticker`, `company_name`, `buzz_score`,
`sentiment_score` -- confirmed live across all four; only the platform-specific
volume fields differ (mentions/unique_posts/subreddit_count for Reddit,
unique_tweets for X, source_count for News, trade_count/market_count/
unique_traders/total_liquidity for Polymarket), none of which this project needs.

No client-side retry loop -- matches `pipelines/macro/frankfurter_client.py`'s
plain single-request style; per-platform resilience lives in `pull_adanos.py`,
matching `pipelines/macro/pull_macro.py`'s established per-item pattern."""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests
from core.settings import settings

BASE_URL = "https://api.adanos.org"
REQUEST_TIMEOUT_SECONDS = 30


class AdanosClient:
    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or settings.adanos_api_key
        if resolved_key is None:
            raise ValueError("ADANOS_API_KEY is not set -- required to use AdanosClient.")
        self._api_key: str = resolved_key
        # Updated after every request -- pull_adanos.py logs this so real monthly
        # usage against the 250/month free-tier budget is always visible.
        self.last_rate_limit_remaining: str | None = None

    def compare(self, tickers: list[str], platform: str) -> pd.DataFrame:
        """Returns columns: ticker, company_name, buzz_score, sentiment_score --
        the four fields every platform's /compare response shares (confirmed live).
        `company_name` is None for a ticker Adanos doesn't recognise at all -- the
        caller is responsible for filtering those out, this method does not."""
        payload = self._get(
            f"/{platform}/stocks/v1/compare", {"tickers": ",".join(tickers)}
        )
        stocks = payload.get("stocks", [])
        if not stocks:
            return pd.DataFrame(columns=["ticker", "company_name", "buzz_score", "sentiment_score"])

        df = pd.DataFrame(stocks)
        return df[["ticker", "company_name", "buzz_score", "sentiment_score"]]

    def trending_sectors(self, platform: str = "reddit") -> pd.DataFrame:
        """Real response shape confirmed live: a bare JSON array (not wrapped in an
        object), each row carrying a `sector` field -- "Energy" is one of the real
        values seen live. No sector-filter query param exists; filtering to Energy
        happens in the caller."""
        rows = self._get_list(f"/{platform}/stocks/v1/trending/sectors", {"limit": 20})
        if not rows:
            return pd.DataFrame(columns=["sector", "buzz_score"])
        df = pd.DataFrame(rows)
        return df[["sector", "buzz_score"]]

    def _request(self, path: str, params: dict[str, Any]) -> requests.Response:
        response = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            headers={"X-API-Key": self._api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        self.last_rate_limit_remaining = response.headers.get("X-RateLimit-Remaining-Monthly")
        return response

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self._request(path, params).json()
        return result

    def _get_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._request(path, params).json()
        return result
