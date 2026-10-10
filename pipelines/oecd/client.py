"""OECD Quarterly National Accounts client -- keyless SDMX, CSV out.

Confirmed live 2026-10-10. The one series this client fetches is seasonally adjusted real
GDP growth on the same quarter a year earlier:

    Q . Y . {areas} ... B1GQ ..... L . GY .
    |   |               |          |   `- TRANSFORMATION: growth on a year earlier
    |   |               |          `----- PRICE_BASE: chain-linked volume, i.e. real
    |   |               `---------------- TRANSACTION: gross domestic product
    |   `-------------------------------- ADJUSTMENT: seasonally adjusted
    `------------------------------------ FREQ: quarterly

China publishes no chain-linked LEVEL on this dataflow -- only nominal levels and the two
growth transformations -- so growth is the only real China series available here.

An unknown area code is the trap. Alone it returns HTTP 404 `NoRecordsFound`; beside a
valid code it returns HTTP 200 with that area silently left out. `EA19`, `EA20` and
`EU27_2020` -- the codes Eurostat and FRED use -- are all unknown here. The euro area is
`EA`. `fetch_real_gdp_growth` therefore checks that every area it asked for came back.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

BASE_URL = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1"
REQUEST_TIMEOUT_SECONDS = 120

_COLUMNS = ["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"]


def real_gdp_growth_key(areas: list[str]) -> str:
    return f"Q.Y.{'+'.join(areas)}...B1GQ.....L.GY."


def fetch_real_gdp_growth(areas: list[str], start_period: str = "2012-Q1") -> pd.DataFrame:
    """One row per area per quarter: `REF_AREA`, `TIME_PERIOD` (`yyyy-Qn`), `OBS_VALUE`
    (percent, float), `OBS_STATUS`. Raises if any requested area is absent."""
    response = requests.get(
        f"{BASE_URL}/{real_gdp_growth_key(areas)}",
        params={"startPeriod": start_period, "format": "csvfile"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    raw = pd.read_csv(io.StringIO(response.text), dtype=str)
    absent_columns = [column for column in _COLUMNS if column not in raw.columns]
    if absent_columns:
        raise ValueError(
            f"OECD response is not the expected SDMX CSV: no {absent_columns} column(s). "
            f"Got columns {list(raw.columns)[:6]}"
        )

    df = raw[_COLUMNS].copy()
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="raise").astype("float64")

    missing = sorted(set(areas) - set(df["REF_AREA"]))
    if missing:
        raise ValueError(
            f"OECD returned no rows for area(s) {missing}. An unknown REF_AREA is omitted "
            f"silently when requested beside a valid one -- the euro area is 'EA', not "
            f"'EA19'/'EA20'/'EU27_2020'."
        )
    return df.reset_index(drop=True)
