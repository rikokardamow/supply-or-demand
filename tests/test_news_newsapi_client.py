from __future__ import annotations

import inspect

import pandas as pd
import pytest
from pipelines.news import pull_news
from pipelines.news.newsapi_client import NewsAPIClient


@pytest.mark.vcr
def test_search_returns_gdelt_compatible_shape_for_a_real_query() -> None:
    df = NewsAPIClient().search("crude oil OPEC", page_size=5)

    assert list(df.columns) == ["url", "title", "seendate", "domain", "language", "sourcecountry"]
    assert not df.empty
    assert pd.api.types.is_datetime64_any_dtype(df["seendate"])
    # Confirmed live: NewsAPI's /everything returns neither a language nor a
    # sourcecountry field -- these are documented no-guess defaults, not omissions.
    assert (df["language"] == "unknown").all()
    assert (df["sourcecountry"] == "").all()


def test_search_returns_empty_conformant_frame_when_no_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pipelines.news.newsapi_client.NewsAPIClient._get",
        lambda self, params: {"status": "ok", "totalResults": 0, "articles": []},
    )

    df = NewsAPIClient(api_key="fake-key").search("no such query")

    assert df.empty
    assert list(df.columns) == ["url", "title", "seendate", "domain", "language", "sourcecountry"]


def test_pull_news_main_never_references_newsapi() -> None:
    """Regression guard for the real ToS constraint (specs/16_newsapi-supplement.md):
    NewsAPI's free tier is dev/testing only, never licensed for the kind of scheduled
    pull `main()` performs. Checking `main`'s own source (not the whole module, which
    legitimately imports NewsAPIClient for `manual_newsapi_search`) is what actually
    proves `main()` itself never calls into NewsAPI."""
    source = inspect.getsource(pull_news.main)
    assert "NewsAPI" not in source


def test_manual_newsapi_search_maps_through_the_existing_tagging_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_articles = pd.DataFrame(
        {
            "url": ["https://example.com/a1"],
            "title": ["Refinery fire halts operations"],
            "seendate": pd.to_datetime(["2026-09-01"]),
            "domain": ["example.com"],
            "language": ["unknown"],
            "sourcecountry": [""],
        }
    )
    monkeypatch.setattr(
        "pipelines.news.newsapi_client.NewsAPIClient.search",
        lambda self, query, page_size=100: fake_articles,
    )

    result = pull_news.manual_newsapi_search(
        NewsAPIClient(api_key="fake-key"), "refinery fire", "crude"
    )

    assert len(result) == 1
    assert result.iloc[0]["source"] == "newsapi"
    assert result.iloc[0]["commodity"] == "crude"
    assert "manual_search" in result.iloc[0]["tags"]
