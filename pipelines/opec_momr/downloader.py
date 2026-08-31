"""Downloads and caches OPEC MOMR Excel appendix files. Confirmed live URL pattern:
https://opec.org/assets/assetdb/momr-appendix-{month}-{year}.xlsx (lowercase full
month name). No API, no key -- a public static file.

A new precedent relative to every other pipeline here (which cache *parsed* data as
Parquet, e.g. pipelines/entsog/directory.py): this caches the raw downloaded file
itself under data/raw/opec/, since the parser needs to re-read real Excel structure
from disk (and the fixture test parses a checked-in copy of exactly this kind of
file) rather than a pre-parsed frame.

Gotcha, confirmed live: a genuinely unpublished/nonexistent month's URL doesn't
return a clean 404 -- opec.org's Cloudflare front returns a 403 "Just a moment..."
JS-challenge page instead. `latest_appendix` treats any non-200 response as "not
published yet" and falls back a month, rather than branching on a specific status
code."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

BASE_URL = "https://opec.org/assets/assetdb"
CACHE_DIR = Path("data/raw/opec")
REQUEST_TIMEOUT_SECONDS = 30


def _slug(month: date) -> str:
    return f"momr-appendix-{month.strftime('%B').lower()}-{month.year}"


def _cache_path(month: date) -> Path:
    return CACHE_DIR / f"{_slug(month)}.xlsx"


def download_appendix(month: date) -> Path:
    """Downloads the MOMR Excel appendix for `month` (only year/month matter --
    pass any date within the target month), caching it under data/raw/opec/.
    Returns the local path unchanged on a cache hit. Raises RuntimeError on
    anything other than a 200 (see module docstring re: the Cloudflare gotcha)."""
    cache_path = _cache_path(month)
    if cache_path.exists():
        return cache_path

    url = f"{BASE_URL}/{_slug(month)}.xlsx"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise RuntimeError(
            f"MOMR appendix unavailable for {month:%B %Y} (HTTP {response.status_code}): {url}"
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return cache_path


def latest_appendix(today: date | None = None) -> Path:
    """Downloads the current month's appendix, falling back to the prior month if
    not yet published (confirmed live: MOMR publishes ~11th-14th each month, so
    early-month runs need last month's issue). Raises RuntimeError if even the
    prior month fails -- that one should always be available, so a failure there
    is a genuine problem, not an early-month timing gap."""
    reference = today or date.today()
    this_month = reference.replace(day=1)
    try:
        return download_appendix(this_month)
    except RuntimeError:
        prior_month = (this_month - timedelta(days=1)).replace(day=1)
        return download_appendix(prior_month)
