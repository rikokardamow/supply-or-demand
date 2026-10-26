"""pipelines/jodi_gas. No cassette, on purpose: the token request carries the account's
username and password in its form body, which a recording would put in a public file. HTTP
is replaced here instead. All figures synthetic."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from pipelines.jodi_gas import client as jodi
from pipelines.jodi_gas.pull import to_rows


class _Response:
    def __init__(self, body: dict[str, Any], status: int = 200) -> None:
        self._body, self.status_code = body, status

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


def _row(country: str, flow: str, date: str, quantity: float | None, unit: str = "M3") -> dict:
    return {"country": country, "product": "NATGAS", "flow": flow, "unit": unit, "date": date,
            "quantity": quantity, "quality": "1"}  # fmt: skip


def test_token_is_form_encoded_and_pages_are_followed(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, **kw: Any) -> _Response:
        calls.append(("post", kw))
        return _Response({"token": "t" * 400, "username": "u", "expires": "x"})

    def get(url: str, **kw: Any) -> _Response:
        calls.append(("get", kw))
        page = int(kw["params"]["pageNumber"])
        return _Response({"data": [_row("JP", "IMPLNG", "2026-0" + str(page), 100.0 * page)],
                          "meta": {"hasNext": page < 2}})  # fmt: skip

    monkeypatch.setattr(jodi.requests, "post", post)
    monkeypatch.setattr(jodi.requests, "get", get)

    frame = jodi.JodiGasClient("me@example.com", "secret-pass").gas_data(flows="IMPLNG")

    assert list(frame["quantity"]) == [100.0, 200.0]
    post_kw = calls[0][1]
    assert "data" in post_kw and "json" not in post_kw  # JSON gets HTTP 400, confirmed live
    assert sum(1 for c in calls if c[0] == "post") == 1  # one token for the whole run
    assert calls[1][1]["headers"]["Authorization"].startswith("Bearer ")


def test_missing_credentials_fail_before_any_request(monkeypatch) -> None:
    monkeypatch.setattr(jodi.settings, "jodi_username", None)
    monkeypatch.setattr(jodi.settings, "jodi_password", None)

    with pytest.raises(ValueError, match="JODI_USERNAME"):
        jodi.JodiGasClient()


def test_only_million_m3_rows_become_series_and_null_is_not_zero() -> None:
    frame = pd.DataFrame(
        [
            _row("JP", "IMPLNG", "2026-08", 7000.0),
            _row("JP", "IMPLNG", "2026-08", 280000.0, unit="TJ"),
            _row("QA", "EXPLNG", "2026-08", None),
        ]
    )

    rows = to_rows(frame, pd.Timestamp("2026-10-26"))

    assert list(rows["series_id"]) == ["jodi_gas.implng.jp"]
    assert rows["unit"].iloc[0] == "mcm"
