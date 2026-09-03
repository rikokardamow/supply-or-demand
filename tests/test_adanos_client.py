from __future__ import annotations

import pytest
from pipelines.adanos.client import AdanosClient


@pytest.mark.vcr
def test_compare_returns_the_four_shared_fields_for_real_tickers() -> None:
    df = AdanosClient().compare(["XOM", "CVX"], platform="reddit")

    assert list(df.columns) == ["ticker", "company_name", "buzz_score", "sentiment_score"]
    assert len(df) == 2
    assert set(df["ticker"]) == {"XOM", "CVX"}
    assert df["company_name"].notna().all()


@pytest.mark.vcr
def test_compare_returns_null_company_name_for_an_unrecognised_ticker() -> None:
    # Confirmed live: Adanos never errors on an unrecognised ticker -- it returns
    # HTTP 200 with a zeroed row and company_name=None. This is the real existence
    # signal pull_adanos.py filters on.
    df = AdanosClient().compare(["NOTAREALTICKER123"], platform="reddit")

    assert len(df) == 1
    assert df.iloc[0]["company_name"] is None


@pytest.mark.vcr
def test_trending_sectors_includes_a_real_energy_row() -> None:
    df = AdanosClient().trending_sectors(platform="reddit")

    assert list(df.columns) == ["sector", "buzz_score"]
    assert "Energy" in set(df["sector"])


def test_last_rate_limit_remaining_is_populated_after_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        status_code = 200

        def __init__(self) -> None:
            self.headers = {"X-RateLimit-Remaining-Monthly": "123"}

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"stocks": []}

    monkeypatch.setattr(
        "pipelines.adanos.client.requests.get", lambda *args, **kwargs: _FakeResponse()
    )

    client = AdanosClient(api_key="fake-key")
    client.compare(["XOM"], platform="reddit")

    assert client.last_rate_limit_remaining == "123"
