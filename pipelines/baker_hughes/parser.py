"""Parses the "NAM Weekly" sheet of Baker Hughes' North America rig count
XLSX into ts_long. Confirmed live: this sheet is already a long, granular table
(one row per country/county/basin/drill-target/location/state/trajectory/week,
~188,000 rows for ~2.7 years of history) -- not a snapshot like OPEC MOMR's
appendix tables, so no vintage-tracking/revision_date scheme is needed here;
ingestion time is used, matching pipelines/eia's convention (no per-row
revision info given).

Aggregated up from the raw per-county rows to three levels (per-county itself
is excessive granularity for any current chart need, and can be added later
straight from the already-cached raw file if it turns out to matter):
- country total (all drill-target/location/trajectory/state summed)
- country x drill-target (oil/gas/miscellaneous) -- matches the spec's own
  example series_id (`bh.rigs.us.oil`) exactly
- country x drill-target x state/province -- one level of regional detail"""

from __future__ import annotations

import re

import openpyxl
import pandas as pd

SHEET_NAME = "NAM Weekly"
_EXPECTED_COLUMNS = [
    "Country", "County", "Basin", "GOM", "DrillFor", "Location",
    "State/Province", "Trajectory", "Year", "Month", "US_PublishDate", "Rig Count Value",
]  # fmt: skip


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", str(label)).strip().lower()
    return re.sub(r"\s+", "_", cleaned)


def _find_header_row(ws: object) -> int:
    """Confirmed live: 10 blank/title rows precede the real header -- detected
    by finding the first row whose first cell is literally "Country", rather
    than hardcoding row 11."""
    for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):  # type: ignore[attr-defined]
        if row and row[0] == "Country":
            return row_num
    raise ValueError(f"Sheet {SHEET_NAME!r}: no header row found (expected a 'Country' column)")


def parse_weekly_rig_counts(path: str, revision_date: pd.Timestamp) -> pd.DataFrame:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(f"Expected sheet {SHEET_NAME!r} not found — layout may have changed")
    ws = wb[SHEET_NAME]

    header_row = _find_header_row(ws)
    header = next(
        row for i, row in enumerate(ws.iter_rows(values_only=True), start=1) if i == header_row
    )
    if list(header[: len(_EXPECTED_COLUMNS)]) != _EXPECTED_COLUMNS:
        raise ValueError(
            f"Sheet {SHEET_NAME!r}: header {list(header[:len(_EXPECTED_COLUMNS)])!r} "
            f"doesn't match the expected columns {_EXPECTED_COLUMNS!r} — layout may have changed"
        )

    rows = [
        row[: len(_EXPECTED_COLUMNS)]
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True)
        if row and row[0] is not None
    ]
    raw = pd.DataFrame(rows, columns=_EXPECTED_COLUMNS)
    raw["Rig Count Value"] = pd.to_numeric(raw["Rig Count Value"], errors="coerce")
    raw = raw.dropna(subset=["Rig Count Value", "US_PublishDate"])
    raw["ts"] = pd.to_datetime(raw["US_PublishDate"])

    frames = []

    country_total = raw.groupby(["Country", "ts"])["Rig Count Value"].sum().reset_index()
    frames.append(
        pd.DataFrame(
            {
                "series_id": "bh.rigs." + country_total["Country"].map(_slug) + ".total",
                "ts": country_total["ts"],
                "value": country_total["Rig Count Value"],
                "geo": country_total["Country"],
            }
        )
    )

    by_drillfor = raw.groupby(["Country", "DrillFor", "ts"])["Rig Count Value"].sum().reset_index()
    frames.append(
        pd.DataFrame(
            {
                "series_id": (
                    "bh.rigs."
                    + by_drillfor["Country"].map(_slug)
                    + "."
                    + by_drillfor["DrillFor"].map(_slug)
                ),
                "ts": by_drillfor["ts"],
                "value": by_drillfor["Rig Count Value"],
                "geo": by_drillfor["Country"],
            }
        )
    )

    by_state = (
        raw.groupby(["Country", "DrillFor", "State/Province", "ts"])["Rig Count Value"]
        .sum()
        .reset_index()
    )
    frames.append(
        pd.DataFrame(
            {
                "series_id": (
                    "bh.rigs."
                    + by_state["Country"].map(_slug)
                    + "."
                    + by_state["DrillFor"].map(_slug)
                    + "."
                    + by_state["State/Province"].map(_slug)
                ),
                "ts": by_state["ts"],
                "value": by_state["Rig Count Value"],
                "geo": by_state["State/Province"],
            }
        )
    )

    df = pd.concat(frames, ignore_index=True)
    df["source"] = "baker_hughes"
    df["unit"] = "rigs"
    df["freq"] = "W"
    df["revision_date"] = revision_date
    return df[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]]
