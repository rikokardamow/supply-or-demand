"""JODI-Oil World Database client -- downloads the annual CSV for one table
("primary" or "secondary") and caches the raw file, mirroring
pipelines/opec_momr's raw-file-caching precedent.

Confirmed live: two annual CSV series exist on jodidata.org -- "primary" (crude
oil + NGL + other crude, flows named INDPROD/REFINOBS/CLOSTLV/etc.) and
"secondary" (refined products like LPG/gasoline/gas-diesel, a different flow
vocabulary: REFGROUT/RECEIPTS/TOTDEMO/etc.). pull_jodi.py reads the primary
table for crude; pull_demand.py reads the secondary table for total product
demand."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv"
TABLES = ("primary", "secondary")
CACHE_DIR = Path("data/raw/jodi")
REQUEST_TIMEOUT_SECONDS = 60


def _csv_url(year: int, is_current_year: bool, table: str = "primary") -> str:
    # Confirmed live for both tables: the current (still-in-progress) year's file is
    # "{table}year{year}.csv", prior closed years are "{year}.csv" -- not one guessable
    # pattern.
    name = f"{table}year{year}.csv" if is_current_year else f"{year}.csv"
    return f"{BASE_URL}/{table}/{name}"


def download_annual_csv(
    year: int, is_current_year: bool, table: str = "primary"
) -> pd.DataFrame:
    """Downloads (or reads from cache) one year's full CSV for `table`.
    Real columns, confirmed live: REF_AREA, TIME_PERIOD, ENERGY_PRODUCT,
    FLOW_BREAKDOWN, UNIT_MEASURE, OBS_VALUE, ASSESSMENT_CODE. `OBS_VALUE` is a
    string column -- "-" means genuinely not reported, "x" means confidential/
    not applicable (e.g. a stock *level* reported under a rate unit like KBD) --
    both non-numeric, both mean "no usable value here", confirmed live.

    The current year's file is a "year to date" file JODI updates monthly (per
    the spec's own "~20th" release note) -- always re-downloaded, never served
    from cache, so the monthly entrypoint actually picks up new months. Prior,
    closed years are cached indefinitely once fetched (their data doesn't grow)."""
    if table not in TABLES:
        raise ValueError(f"unknown JODI table {table!r}; expected one of {TABLES}")
    cache_path = CACHE_DIR / f"jodi-{table}-{year}.csv"
    if is_current_year or not cache_path.exists():
        url = _csv_url(year, is_current_year, table)
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)

    return pd.read_csv(cache_path, dtype={"OBS_VALUE": str})
