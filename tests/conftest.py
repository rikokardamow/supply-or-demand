from __future__ import annotations

import json

import pytest


def _scrub_echoed_api_key(response: dict) -> dict:
    """EIA's API echoes api_key back inside the JSON response body itself
    (response.request.params.api_key) — filter_query_parameters alone doesn't
    catch that. Scrub it here so it never lands in a committed cassette."""
    body = response.get("body", {})
    raw = body.get("string")
    if not raw:
        return response

    try:
        payload = json.loads(raw)
    except ValueError:
        return response

    params = payload.get("request", {}).get("params", {})
    if "api_key" in params:
        params["api_key"] = "FILTERED"
        body["string"] = json.dumps(payload).encode("utf-8")

    return response


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["api_key"],
        "filter_headers": ["x-key"],  # GIE's auth header (EIA uses a query param instead)
        "before_record_response": _scrub_echoed_api_key,
    }
