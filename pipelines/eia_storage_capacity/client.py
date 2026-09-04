"""EIA's "Working and Net Available Shell Storage Capacity" report -- confirmed live this
session: discontinued as of the March 2024 data (eia.gov/petroleum/storagecapacity's own
words: "We have discontinued publication of..."), but the historical workbook is still a
real, live download with a dedicated Cushing sheet, semi-annual (Mar/Sep) 2011-03-31 to
2024-03-01. Not an API route -- confirmed by walking EIA's own v2 API route tree (petroleum/
stoc, petroleum/crd, every top-level category) and finding no capacity route anywhere."""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pandas as pd
import requests

REPORT_URL = "https://www.eia.gov/petroleum/storagecapacity/crudeoilstorage.xlsx"

# The exact row label this project needs -- EIA's own footnote 3 on this row: "may be used
# as an estimate of total commercial crude oil storage capacity... where details by storage
# facility are unavailable" -- precisely this project's situation, since the existing lake's
# weekly Cushing stocks series (W_EPC0_SAX_YCUOK_MBBL, pipelines/eia/pull_wpsr.py) is a
# single undifferentiated total, not split tank-vs-pipeline. Matched by prefix, not an exact
# row number, since row position in a hand-maintained government workbook isn't something to
# assume stays fixed even though this particular file is now frozen/discontinued.
_CAPACITY_ROW_LABEL_PREFIX = "Sum of Working Storage Capacity and Stocks in Transit"


def fetch_cushing_capacity(url: str = REPORT_URL) -> pd.DataFrame:
    """Returns columns: ts, value (thousand barrels, matching the lake's existing MBBL-scale
    convention for this series). One row per semi-annual report date, 2011-03-31 to
    2024-03-01 -- the report's own last published data, confirmed live; there is nothing
    newer to fetch."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    workbook = openpyxl.load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["Cushing"]

    dates_row = None
    capacity_row = None
    for row in sheet.iter_rows():
        label = row[0].value
        if isinstance(label, str) and label.strip().startswith(_CAPACITY_ROW_LABEL_PREFIX):
            capacity_row = row
        # The header row is the one whose non-first cells are all dates.
        rest = [c.value for c in row[1:] if c.value is not None]
        if rest and all(hasattr(v, "year") for v in rest):
            dates_row = row

    if dates_row is None or capacity_row is None:
        raise ValueError(
            "Cushing sheet layout has changed -- expected a date header row and a row "
            f"starting {_CAPACITY_ROW_LABEL_PREFIX!r}, found neither/one only"
        )

    dates = []
    values = []
    for date_cell, capacity_cell in zip(dates_row[1:], capacity_row[1:], strict=True):
        if date_cell.value is None or capacity_cell.value is None:
            continue
        dates.append(pd.Timestamp(date_cell.value))
        values.append(float(capacity_cell.value))

    return pd.DataFrame({"ts": dates, "value": values})
