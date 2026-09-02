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

    if not isinstance(payload, dict):
        # Some APIs (e.g. Open-Meteo's batched multi-city responses) return a
        # top-level JSON array, not an object -- nothing to scrub, and EIA's own
        # echoed-api_key body this hook targets is always a dict.
        return response

    params = payload.get("request", {}).get("params", {})
    if "api_key" in params:
        params["api_key"] = "FILTERED"
        body["string"] = json.dumps(payload).encode("utf-8")

    return response


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": [
            "api_key",
            "api-key",  # Guardian Open Platform's own param name (pipelines/news)
            "securityToken",
            "_",  # CAISO's cache-busting timestamp param (confirmed live) -- changes
            # every request, which breaks vcrpy's default query-string cassette
            # matching on replay unless stripped from both sides the same way.
        ],
        "filter_headers": ["x-key"],  # GIE's auth header (EIA uses a query param instead)
        "before_record_response": _scrub_echoed_api_key,
    }
