"""Frankfurter FX client -- free, no key, ECB reference rates. Real response shape
confirmed live: {"amount": 1, "base": "USD", "start_date": "...", "end_date": "...",
"rates": {"<date>": {"<ccy>": <rate>, ...}, ...}} -- rates is keyed by date, each
holding a {currency: rate} dict (not a flat top-level object). This is the ECB's own
daily reference rate by construction (Frankfurter's whole purpose), so a given date's
value matches ECB's published rate by definition."""

from __future__ import annotations

from datetime import date

import pandas as pd
import requests

BASE_URL = "https://api.frankfurter.dev/v1"
REQUEST_TIMEOUT_SECONDS = 30


class FrankfurterClient:
    def get_rates(self, start: date, end: date, symbols: list[str]) -> pd.DataFrame:
        """Returns columns: ts, currency, rate -- "how many `currency` you get for 1
        USD" (base=USD always; see pipelines/macro/NOTES.md for why this project uses
        a uniform USD-base convention rather than per-pair market quote direction)."""
        url = f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}"
        params = {"base": "USD", "symbols": ",".join(symbols)}
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()

        rows = [
            {"ts": pd.Timestamp(day), "currency": ccy, "rate": rate}
            for day, day_rates in payload["rates"].items()
            for ccy, rate in day_rates.items()
        ]
        return pd.DataFrame(rows, columns=["ts", "currency", "rate"])
