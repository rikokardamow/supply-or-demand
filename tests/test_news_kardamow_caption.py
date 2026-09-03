from __future__ import annotations

import pandas as pd
import pytest
from pipelines.news.kardamow_caption import CACHE_PATH, generate_kardamow_caption


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_generate_kardamow_caption_raises_clearly_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr("pipelines.news.kardamow_caption.settings.anthropic_api_key", None)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        generate_kardamow_caption("e1", "Headline", "crude", ["outage"], 2, "NL")


def test_generate_kardamow_caption_returns_a_cached_value_without_calling_the_api(
    monkeypatch,
) -> None:
    # No key set at all -- if this reached the real API call it would raise the
    # RuntimeError above instead of returning the cached value, so a passing test here
    # confirms the cache short-circuits before ever touching settings/the client.
    monkeypatch.setattr("pipelines.news.kardamow_caption.settings.anthropic_api_key", None)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"event_id": "e2", "caption": "Cached take."}]).to_parquet(
        CACHE_PATH, index=False
    )

    result = generate_kardamow_caption("e2", "Headline", "crude", ["outage"], 2, "NL")

    assert result == "Cached take."
