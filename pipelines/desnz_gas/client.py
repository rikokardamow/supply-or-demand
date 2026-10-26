"""DESNZ Energy Trends section 4 (UK natural gas): find the current workbooks, parse them.

Keyless. Each monthly release publishes new files under new media ids, so the links are
read from the GOV.UK statistics page every run and never hard-coded. Confirmed live
2026-10-26 (see this package's CLAUDE.md):

- ``ET_4.2_<MON>_<YY>.xlsx``, sheet ``Month (mcm)``: monthly supply and demand from 2008.
- ``ET_4.3_<MON>_<YY>.xlsx``, sheet ``Data in flat format``: imports and exports by type,
  country and pipeline, monthly from 2000. ET 4.4 carries the same flat sheet.
"""

from __future__ import annotations

import io
import re
from typing import Any

import openpyxl
import pandas as pd
import requests

PAGE_URL = "https://www.gov.uk/government/statistics/gas-section-4-energy-trends"
REQUEST_TIMEOUT_SECONDS = 120
HEADERS = {"User-Agent": "Mozilla/5.0 (energy-dashboard; public statistics)"}
MISSING = "[x]"  # DESNZ's marker for "not available"

# ET 4.2 "Month (mcm)" header text (before any line break or [note]) -> this repo's name.
BALANCE_COLUMNS: dict[str, str] = {
    "Gross production": "production",
    "Imports": "imports",
    "Exports": "exports",
    "Net imports": "net_imports",
    "Stock change": "stock_change",  # positive = withdrawal from storage (the UK convention)
    "Synthetic coke oven gas": "synthetic",
    "Biomethane to grid": "biomethane",
    "Gross Supply": "gross_supply",
    "Net supply": "net_supply",
    "Electricity generation": "power",
    "Domestic": "domestic",
    "Industrial": "industrial",
    "Services": "services",
    "Producer own use": "producer_own_use",
    "Operator own use": "operator_own_use",
    "LNG own use": "lng_own_use",
    "Storage own use": "storage_own_use",
    "Other": "other",
    "Demand": "demand",
}


def discover_links(page_html: str) -> dict[str, str]:
    """``{"4.2": url, "4.3": url}`` from the statistics page. Raises if either is missing:
    a page redesign must fail loudly, not quietly skip the UK."""
    links: dict[str, str] = {}
    for table in ("4.2", "4.3"):
        pattern = rf"https://assets\.publishing\.service\.gov\.uk/[^\"'\s]+/ET_{re.escape(table)}_[A-Z]{{3}}_\d{{2}}\.xlsx"
        found = sorted(set(re.findall(pattern, page_html)))
        if len(found) != 1:
            raise ValueError(f"ET {table}: expected one workbook link, found {found}")
        links[table] = found[0]
    return links


def _header_name(cell: Any) -> str:
    return re.split(r"\n|\[", str(cell))[0].strip()


def parse_monthly_balance(content: bytes) -> pd.DataFrame:
    """ET 4.2 ``Month (mcm)`` -> long rows ``line``, ``ts`` (month start), ``value`` (mcm),
    ``provisional``. The month comes from the sheet's numeric month and year columns, because
    the label of a provisional month is "[provisional] July 2026". ``[x]`` cells give no row."""
    ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)["Month (mcm)"]
    rows = list(ws.iter_rows(values_only=True))
    header_at = next(i for i, r in enumerate(rows) if r and str(r[0]).strip() == "Month")
    header = [_header_name(c) if c is not None else None for c in rows[header_at]]
    # The trailing helper columns read M (name), M (number), Q, Q, Y.
    month_col = max(i for i, h in enumerate(header) if h == "M")
    year_col = max(i for i, h in enumerate(header) if h == "Y")
    columns = {i: BALANCE_COLUMNS[h] for i, h in enumerate(header) if h in BALANCE_COLUMNS}
    if set(columns.values()) != set(BALANCE_COLUMNS.values()):
        missing = set(BALANCE_COLUMNS.values()) - set(columns.values())
        raise ValueError(f"ET 4.2: columns not found: {sorted(missing)}")
    out = []
    for row in rows[header_at + 1 :]:
        if row is None or row[year_col] in (None, "") or row[month_col] in (None, ""):
            continue
        ts = pd.Timestamp(year=int(row[year_col]), month=int(row[month_col]), day=1)
        provisional = "provisional" in str(row[0]).lower()
        for i, line in columns.items():
            value = row[i]
            if value in (None, "", MISSING):
                continue
            out.append((line, ts, float(value), provisional))
    return pd.DataFrame(out, columns=["line", "ts", "value", "provisional"])


def parse_trade(content: bytes) -> pd.DataFrame:
    """ET 4.3 ``Data in flat format`` -> ``flow`` (imports/exports/net), ``type``, ``country``,
    ``pipeline``, ``ts``, ``value`` (mcm). Totals are kept, because they check the parts."""
    ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)[
        "Data in flat format"
    ]
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    at = {name: header.index(name) for name in ("Year", "M", "Import/export", "Type",
                                                 "Country", "Pipeline", "mcm")}  # fmt: skip
    flows = {"Import": "imports", "Export": "exports", "Net Import": "net"}
    out = []
    for row in rows:
        if row is None or row[at["Year"]] in (None, ""):
            continue
        value = row[at["mcm"]]
        if value in (None, "", MISSING):
            continue
        out.append(
            (
                flows[str(row[at["Import/export"]]).strip()],
                str(row[at["Type"]]).strip(),
                str(row[at["Country"]]).strip(),
                str(row[at["Pipeline"]]).strip(),
                pd.Timestamp(year=int(row[at["Year"]]), month=int(row[at["M"]]), day=1),
                float(value),
            )
        )
    return pd.DataFrame(out, columns=["flow", "type", "country", "pipeline", "ts", "value"])


class DesnzGasClient:
    def _get(self, url: str) -> requests.Response:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response

    def links(self) -> dict[str, str]:
        return discover_links(self._get(PAGE_URL).text)

    def workbook(self, url: str) -> bytes:
        return self._get(url).content
