"""EU ETS public data: EEX primary auctions and the Union Registry's installation file.

Keyless. Both confirmed live 2026-10-26 (see this package's NOTES.md):

- EEX publishes one xlsx per year of primary auctions, 2020 onwards, at a fixed URL pattern.
  An auction clearing price is official and daily, but it is an auction print, not a
  continuous market price. Label it that way everywhere.
- The European Commission publishes ``verified_emissions_<year>_en.xlsx``: one row per
  installation, aircraft operator or shipping company, with allocation and verified
  emissions for every year since 2008. Its download link changes with each release, so it is
  read from the Union Registry page.
"""

from __future__ import annotations

import io
import re
from typing import Any

import openpyxl
import pandas as pd
import requests

EEX_URL = (
    "https://public.eex-group.com/eex/eua-auction-report/"
    "emission-spot-primary-market-auction-report-{year}-data.xlsx"
)
FIRST_EEX_YEAR = 2020  # earlier years 404 at this pattern (checked 2012-2019)
REGISTRY_PAGE = (
    "https://climate.ec.europa.eu/eu-action/carbon-markets/"
    "eu-emissions-trading-system-eu-ets/union-registry_en"
)
REGISTRY_HOST = "https://climate.ec.europa.eu"
REQUEST_TIMEOUT_SECONDS = 180
HEADERS = {"User-Agent": "Mozilla/5.0 (energy-dashboard; public statistics)"}

# EEX header text -> this repo's column name.
EEX_COLUMNS: dict[str, str] = {
    "Date": "date",
    "Auction Name": "auction",
    "Contract": "contract",
    "Status": "status",
    "Auction Price €/tCO2": "price",
    "Auction Volume tCO2": "volume",
    "Total Amount of Bids": "bids_volume",
    "Cover Ratio": "cover_ratio",
    "Total Number of Bidders": "bidders",
    "Total Revenue €": "revenue",
}

# Registry activity codes -> sector. 1 and 20 are combustion of fuels (old and new codes);
# 10 aviation; 50 shipping; every other installation code is industry.
COMBUSTION_CODES = frozenset({1, 20})
AVIATION_CODES = frozenset({10})
MARITIME_CODES = frozenset({50})
# Free allocation to stationary installations, per the file's Read Me: Article 10a(1),
# the new entrant reserve (10a(7)) and electricity modernisation (10c).
FREE_ALLOCATION = ("ALLOCATION", "ALLOCATION_RESERVE", "ALLOCATION_TRANSITIONAL")
UNDOCUMENTED_ALLOCATION = ("ALLOCATION_FEETS", "ALLOCATION_BYICELAND")


def sector_of(code: object) -> str:
    try:
        number = int(str(code))
    except ValueError:
        return "unknown"
    if number in COMBUSTION_CODES:
        return "combustion"
    if number in AVIATION_CODES:
        return "aviation"
    if number in MARITIME_CODES:
        return "maritime"
    return "industry"


def _number(cell: object) -> float | None:
    """Registry cells are text: a number, ``n/a`` (nothing allocated or verified) or
    ``Excluded``. Only a number is a value; ``n/a`` is not zero."""
    try:
        return float(str(cell).replace(",", ""))
    except ValueError:
        return None


def parse_eex(content: bytes) -> pd.DataFrame:
    """One EEX yearly report -> one row per auction with ``EEX_COLUMNS``. A cancelled auction
    is kept with its status, and its price is NaN."""
    ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header_at, offset = next((i, r.index("Date")) for i, r in enumerate(rows) if r and "Date" in r)
    header = [str(c).strip() if c is not None else "" for c in rows[header_at]]
    at = {name: header.index(src) for src, name in EEX_COLUMNS.items() if src in header}
    missing = set(EEX_COLUMNS.values()) - set(at)
    if missing:
        raise ValueError(f"EEX: columns not found: {sorted(missing)}")
    out: list[dict[str, Any]] = []
    for row in rows[header_at + 1 :]:
        if row is None or len(row) <= offset or row[offset] in (None, ""):
            continue
        record = {name: row[i] for name, i in at.items()}
        record["date"] = pd.Timestamp(record["date"]).normalize()
        for col in ("price", "volume", "bids_volume", "cover_ratio", "bidders", "revenue"):
            record[col] = _number(record[col]) if record[col] not in (None, "") else None
        out.append(record)
    return pd.DataFrame(out, columns=list(EEX_COLUMNS.values()))


def discover_registry_link(page_html: str) -> tuple[int, str]:
    """``(year, absolute url)`` of the newest ``verified_emissions_<year>_en.xlsx`` link."""
    found = re.findall(
        r'href="(/document/download/[^"]+?filename=verified_emissions_(\d{4})_en\.xlsx)"',
        page_html,
    )
    if not found:
        raise ValueError("registry page: no verified_emissions_<year>_en.xlsx link")
    path, year = max(found, key=lambda f: int(f[1]))
    return int(year), REGISTRY_HOST + path.replace("&amp;", "&")


def parse_registry(content: bytes) -> pd.DataFrame:
    """Installation rows -> totals by ``registry``, ``sector``, ``year`` and ``metric``.

    Metrics: ``verified_emissions``, ``free_allocation`` (the three documented families),
    ``allocation_feets`` and ``allocation_byiceland`` (undocumented, kept apart),
    ``reporting`` (count of accounts with a numeric verified emission). Swiss (``CH_``)
    columns are left out: they are the Swiss ETS. Values in tonnes (allowances).
    """
    ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)["data"]
    rows = ws.iter_rows(values_only=True)
    header: list[str] = []
    for row in rows:
        if row and "REGISTRY_CODE" in row:
            header = [str(c) if c is not None else "" for c in row]
            break
    if not header:
        raise ValueError("registry: header row not found")
    ix = {name: i for i, name in enumerate(header)}
    pattern = re.compile(r"^(VERIFIED_EMISSIONS|ALLOCATION(?:_[A-Z]+)?)_?(\d{4})$")
    columns = [(m.group(1), int(m.group(2)), i) for name, i in ix.items()
               if (m := pattern.match(name))]  # fmt: skip
    totals: dict[tuple[str, str, int, str], float] = {}
    for row in rows:
        if row is None or row[ix["REGISTRY_CODE"]] in (None, ""):
            continue
        registry = str(row[ix["REGISTRY_CODE"]]).strip()
        sector = sector_of(row[ix["MAIN_ACTIVITY_TYPE_CODE"]])
        for family, year, i in columns:
            value = _number(row[i])
            if value is None:
                continue
            if family == "VERIFIED_EMISSIONS":
                metrics = [("verified_emissions", value), ("reporting", 1.0)]
            elif family in FREE_ALLOCATION:
                metrics = [("free_allocation", value)]
            elif family in UNDOCUMENTED_ALLOCATION:
                metrics = [(family.lower(), value)]
            else:
                continue
            for metric, v in metrics:
                key = (registry, sector, year, metric)
                totals[key] = totals.get(key, 0.0) + v
    frame = pd.DataFrame(
        [(*k, v) for k, v in totals.items()],
        columns=["registry", "sector", "year", "metric", "value"],
    )
    return frame.sort_values(["metric", "sector", "registry", "year"]).reset_index(drop=True)


class CarbonClient:
    def _get(self, url: str) -> requests.Response:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response

    def eex_report(self, year: int) -> bytes | None:
        """The year's EEX workbook, or None if EEX has not published one (404)."""
        response = requests.get(
            EEX_URL.format(year=year), headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    def registry_link(self) -> tuple[int, str]:
        return discover_registry_link(self._get(REGISTRY_PAGE).text)

    def registry_file(self, url: str) -> bytes:
        return self._get(url).content
