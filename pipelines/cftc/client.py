"""CFTC Commitments of Traders -- Disaggregated Futures-Only report, via the Public
Reporting Environment's own Socrata dataset. Confirmed live this session (no API key
needed -- see NOTES.md for the real, inspected response shape and a documented field-name
quirk)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
PAGE_SIZE = 5000

# Real CFTC contract codes, confirmed live this session via a grouped query against the
# dataset itself (not guessed from any name) -- "lco" (ICE Brent) gets a final live
# spot-check in this pipeline's own NOTES.md before being trusted for real trading use.
CONTRACT_CODES: dict[str, str] = {
    "cl": "067651",  # WTI-PHYSICAL
    "rb": "111659",  # GASOLINE RBOB
    "ho": "022651",  # NY HARBOR ULSD
    "lco": "06765T",  # BRENT LAST DAY
}

_OUTPUT_COLUMNS = ["date", "root", "mm_long", "mm_short", "prod_merc_long", "prod_merc_short", "oi"]


class CFTCClient:
    def get_disaggregated(
        self, root: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        """Returns columns: date, root, mm_long, mm_short, prod_merc_long,
        prod_merc_short, oi -- one row per weekly report date."""
        if root not in CONTRACT_CODES:
            raise ValueError(
                f"root={root!r} not recognised -- expected one of {sorted(CONTRACT_CODES)}"
            )
        code = CONTRACT_CODES[root]

        clauses = [f"cftc_contract_market_code='{code}'"]
        if start is not None:
            clauses.append(f"report_date_as_yyyy_mm_dd>='{start.isoformat()}'")
        if end is not None:
            clauses.append(f"report_date_as_yyyy_mm_dd<='{end.isoformat()}'")
        where = " AND ".join(clauses)

        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            params: dict[str, Any] = {
                "$where": where,
                "$order": "report_date_as_yyyy_mm_dd",
                "$limit": PAGE_SIZE,
                "$offset": offset,
            }
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            page = response.json()
            rows.extend(page)

            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        if not rows:
            return pd.DataFrame(columns=_OUTPUT_COLUMNS)

        df = pd.DataFrame(rows)
        result = pd.DataFrame(
            {
                "date": pd.to_datetime(df["report_date_as_yyyy_mm_dd"]),
                "root": root,
                "mm_long": df["m_money_positions_long_all"].astype(float),
                "mm_short": df["m_money_positions_short_all"].astype(float),
                "prod_merc_long": df["prod_merc_positions_long"].astype(float),
                "prod_merc_short": df["prod_merc_positions_short"].astype(float),
                "oi": df["open_interest_all"].astype(float),
            }
        )
        return result.sort_values("date").reset_index(drop=True)
