"""Downloads and caches Baker Hughes' current weekly North America rig count
XLSX. No API, no key -- but also **no stable, guessable URL** (unlike OPEC's
MOMR appendix): confirmed live, the file lives at
`rigcount.bakerhughes.com/static-files/{uuid}`, a fresh random UUID each week.
The only reliable way to find the current file is to scrape the rig count
landing page for the link labelled "North America Rig Count Report - New
Report" -- a stable label Baker Hughes itself uses to mark the current report,
distinct from the archived "(2013-Aug 2025)"-suffixed one right below it."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LANDING_PAGE_URL = "https://rigcount.bakerhughes.com/na-rig-count"
_CURRENT_REPORT_LABEL = "North America Rig Count Report - New Report"
CACHE_DIR = Path("data/raw/baker_hughes")
REQUEST_TIMEOUT_SECONDS = 60

_FILENAME_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def find_current_report_url() -> str:
    response = requests.get(LANDING_PAGE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    for link in soup.find_all("a", href=lambda h: h and "static-files" in h):
        if link.get_text(strip=True) == _CURRENT_REPORT_LABEL:
            href = str(link["href"])
            return urljoin(LANDING_PAGE_URL, href)

    raise ValueError(
        f"Could not find a link labelled {_CURRENT_REPORT_LABEL!r} on {LANDING_PAGE_URL} "
        f"— the page layout may have changed"
    )


def _report_date_from_disposition(disposition: str) -> str:
    match = _FILENAME_DATE_RE.search(disposition)
    if not match:
        raise ValueError(
            f"Could not find a MM-DD-YYYY date in Content-Disposition: {disposition!r}"
        )
    month, day, year = match.groups()
    return f"{year}-{month}-{day}"


def download_current_report() -> tuple[Path, str]:
    """Returns (cached local path, report date as 'YYYY-MM-DD'). The report
    date is read from the response's own Content-Disposition filename
    (confirmed live: e.g. "08-28-2026 North_America Rig_Count Report.xlsx"),
    not guessed from today's date -- the file may be a few days newer/older
    than "now" depending on exactly when this runs relative to Friday.

    A HEAD request resolves the report date first (confirmed live: this
    server returns the same Content-Disposition header on HEAD as on GET,
    with no response body) -- avoids re-downloading the full ~8 MB file on a
    cache hit, unlike a plain GET-then-check."""
    url = find_current_report_url()
    head = requests.head(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    head.raise_for_status()
    report_date = _report_date_from_disposition(head.headers.get("Content-Disposition", ""))

    cache_path = CACHE_DIR / f"rig-count-{report_date}.xlsx"
    if not cache_path.exists():
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)

    return cache_path, report_date
