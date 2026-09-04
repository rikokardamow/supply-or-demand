from __future__ import annotations

import pandas as pd
import pytest
import requests
from pipelines.adanos.pull_adanos import pull_platform, pull_sector_trend


class _FakeClient:
    """Simulates one platform's compare() failing outright while the ticker basket's
    other batches succeed -- pull_platform must not abort the whole platform pull
    just because one batch failed (matches pipelines/macro/pull_macro.py's own
    per-item resilience precedent)."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_rate_limit_remaining = "200"

    def compare(self, tickers: list[str], platform: str) -> pd.DataFrame:
        self.calls += 1
        if self.calls == 1:
            raise requests.exceptions.RequestException("simulated failure")
        return pd.DataFrame(
            {
                "ticker": tickers,
                "company_name": [f"{t} Corp" for t in tickers],
                "buzz_score": [50.0] * len(tickers),
                "sentiment_score": [0.1] * len(tickers),
            }
        )

    def trending_sectors(self, platform: str = "reddit") -> pd.DataFrame:
        return pd.DataFrame({"sector": ["Energy", "Financials"], "buzz_score": [42.0, 10.0]})


def test_pull_platform_survives_one_failed_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipelines.adanos.pull_adanos.TICKERS",
        {f"T{i}": "US" for i in range(15)},  # 15 tickers -> 2 batches of <=10
    )
    client = _FakeClient()
    ingested_at = pd.Timestamp("2026-09-03")

    result = pull_platform(client, "reddit", ingested_at)

    assert client.calls == 2
    # First batch failed entirely -- only the second batch's rows should be present.
    assert not result.empty
    assert result["series_id"].str.startswith("adanos.reddit.").all()


def test_pull_platform_skips_unrecognised_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipelines.adanos.pull_adanos.TICKERS", {"REAL": "US", "FAKE": "US"})

    class _MixedClient:
        last_rate_limit_remaining = "249"

        def compare(self, tickers: list[str], platform: str) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "ticker": ["REAL", "FAKE"],
                    "company_name": ["Real Corp", None],
                    "buzz_score": [55.0, 0.0],
                    "sentiment_score": [0.2, None],
                }
            )

    result = pull_platform(_MixedClient(), "reddit", pd.Timestamp("2026-09-03"))

    assert "adanos.reddit.real.buzz_score" in set(result["series_id"])
    assert not any("fake" in s for s in result["series_id"])


def test_pull_platform_skips_null_sentiment_but_keeps_buzz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipelines.adanos.pull_adanos.TICKERS", {"XOM": "US"})

    class _NoSentimentClient:
        last_rate_limit_remaining = "249"

        def compare(self, tickers: list[str], platform: str) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "ticker": ["XOM"],
                    "company_name": ["Exxon Mobil Corp"],
                    "buzz_score": [0.0],
                    "sentiment_score": [None],
                }
            )

    result = pull_platform(_NoSentimentClient(), "reddit", pd.Timestamp("2026-09-03"))

    series_ids = set(result["series_id"])
    assert "adanos.reddit.xom.buzz_score" in series_ids
    assert "adanos.reddit.xom.sentiment_score" not in series_ids


def test_pull_sector_trend_filters_to_the_energy_row() -> None:
    result = pull_sector_trend(_FakeClient(), pd.Timestamp("2026-09-03"))

    assert len(result) == 1
    assert result.iloc[0]["value"] == 42.0
    assert result.iloc[0]["series_id"] == "adanos.reddit.sector_energy.buzz_score"
