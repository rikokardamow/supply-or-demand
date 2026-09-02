from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from pipelines.news.guardian_client import GuardianClient

# Crafted against Guardian's own public API reference
# (https://open-platform.theguardian.com/documentation/) -- NOT a live-recorded
# response, since GUARDIAN_KEY is unset. See pipelines/news/NOTES.md: this shape
# still needs live confirmation once a real key is available.
_FAKE_RESPONSE = {
    "response": {
        "status": "ok",
        "total": 1,
        "results": [
            {
                "id": "business/2026/sep/01/refinery-fire-rotterdam",
                "type": "article",
                "sectionId": "business",
                "sectionName": "Business",
                "webPublicationDate": "2026-09-01T10:00:00Z",
                "webTitle": "Refinery fire halts Rotterdam plant",
                "webUrl": "https://www.theguardian.com/business/2026/sep/01/refinery-fire-rotterdam",
                "apiUrl": "https://content.guardianapis.com/business/2026/sep/01/refinery-fire-rotterdam",
            }
        ],
    }
}


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._payload


def test_search_returns_gdelt_compatible_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipelines.news.guardian_client.requests.get",
        lambda *args, **kwargs: _FakeResponse(_FAKE_RESPONSE),
    )

    df = GuardianClient(api_key="fake-key").search("refinery fire")

    assert list(df.columns) == ["url", "title", "seendate", "domain", "language", "sourcecountry"]
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Refinery fire halts Rotterdam plant"
    assert df.iloc[0]["domain"] == "theguardian.com"
    assert pd.api.types.is_datetime64_any_dtype(df["seendate"])


def test_search_returns_empty_conformant_frame_when_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_response = {"response": {"status": "ok", "total": 0, "results": []}}
    monkeypatch.setattr(
        "pipelines.news.guardian_client.requests.get",
        lambda *args, **kwargs: _FakeResponse(empty_response),
    )

    df = GuardianClient(api_key="fake-key").search("no such query")

    assert df.empty
    assert list(df.columns) == ["url", "title", "seendate", "domain", "language", "sourcecountry"]
