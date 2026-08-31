"""Parses the OPEC MOMR Excel appendix's 5 data sheets into ts_long-shaped frames.
Every labelled row with at least one real period value is captured (not a curated
subset, per explicit direction) -- series_id is built from each row's own
section/hierarchy context so identical labels in different sections (e.g.
"Americas" under both World demand and Non-DoC liquids production) stay distinct.

Known simplification: `geo` is "WORLD" for every row here, even though many rows
are genuinely country-level (Table 11-4/11-5). The full location/breakdown detail
still lives in `series_id` (e.g. "momr.nondoc_production.us") for anyone filtering
by it; per-row geo-tagging would need a country-name canonicalisation pass, out of
scope for this session. Sheet map, gotchas, and the anchor-row list are documented
in pipelines/opec_momr/CLAUDE.md."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

_QUARTER_RE = re.compile(r"^([1-4])Q(\d{2})$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# (sheet name, table_slug, expected title substring, default unit, anchor row
# labels that must be present -- the fail-loudly layout-drift guard, since every
# *other* row is captured generically rather than against a fixed list).
_SHEETS: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    (
        "Table 11 - 1",
        "demand_balance",
        "World oil demand and production balance",
        "mb/d",
        (
            "(a) Total world demand",
            "Oil-on-water",
            "OPEC crude oil production \n(secondary sources)",
        ),
    ),
    (
        "Table 11 - 2",
        "demand_balance_revision",
        "changes from last month's table",
        "mb/d",
        ("(a) Total world demand",),
    ),
    (
        "Table 11 - 3",
        "oecd_stocks",
        "OECD oil stocks and oil on water",
        "mb",
        ("OECD total", "Oil-on-water"),
    ),
    (
        "Table 11 - 4",
        "nondoc_production",
        "Non-DoC liquids production and DoC natural gas liquids",
        "mb/d",
        ("US", "DoC NGLs"),
    ),
    (
        "Table 11 - 5",
        "rig_count",
        "World rig count",
        "units",
        ("Total OECD",),
    ),
]

# Sheets whose row hierarchy is encoded across two label columns (col B main item,
# col C its regional/country breakdown) rather than leading-whitespace-in-one-
# column -- confirmed live, Table 11-3 only.
_TWO_LABEL_COLUMN_SHEETS = {"Table 11 - 3"}

_UNIT_HINTS = [
    ("mb/d", "mb/d"),
    ("mb", "mb"),
    ("days", "days"),
    ("units", "units"),
]


def _is_numeric(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", str(label)).strip().lower()
    return re.sub(r"\s+", "_", cleaned)


_FREQ_SUFFIX = {"A": "annual", "Q": "quarterly", "M": "monthly"}


def _series_id_with_freq(base: str, freq: str) -> str:
    # Confirmed live: an annual column ("2026") and a quarterly column ("1Q26")
    # both map to the same representative timestamp (2026-01-01), which would
    # silently collide under ts_long's (series_id, ts) de-dup key otherwise --
    # each granularity gets its own series_id instead.
    return f"{base}.{_FREQ_SUFFIX[freq]}"


def _infer_unit(label: str, default: str) -> str:
    lower = label.lower()
    for hint, unit in _UNIT_HINTS:
        if hint in lower:
            return unit
    return default


def _period_to_ts_freq(value: Any) -> tuple[pd.Timestamp, str] | None:
    if isinstance(value, datetime):
        return pd.Timestamp(value), "M"
    # Confirmed live: annual period headers are real ints (2023), not strings --
    # only quarter labels ("1Q26") come back as strings. bool is an int subclass
    # in Python, so exclude it explicitly (openpyxl can hand back True/False for
    # unrelated formatted cells).
    if isinstance(value, int) and not isinstance(value, bool) and _YEAR_RE.match(str(value)):
        return pd.Timestamp(int(value), 1, 1), "A"
    if not isinstance(value, str):
        return None
    text = value.strip()
    if _YEAR_RE.match(text):
        return pd.Timestamp(int(text), 1, 1), "A"
    match = _QUARTER_RE.match(text)
    if match:
        quarter, yy = int(match.group(1)), int(match.group(2))
        year = 2000 + yy
        month = (quarter - 1) * 3 + 1
        return pd.Timestamp(year, month, 1), "Q"
    return None


def _find_header_row(
    ws: Any, max_scan_rows: int = 10
) -> tuple[int, dict[int, tuple[pd.Timestamp, str]]]:
    """Header-row position varies by sheet (confirmed live: row 4 for some, row 5
    for others, 0-indexed) -- detected by scanning for >=2 cells that parse as
    period labels, not hardcoded per sheet. Returns the 1-indexed row number too,
    so data-row walking can start strictly after it -- otherwise the header row's
    own year/quarter cells get misread as a data row's values (confirmed live)."""
    for row_num, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_scan_rows, values_only=True), start=1
    ):
        periods = {}
        for col_idx, cell in enumerate(row):
            parsed = _period_to_ts_freq(cell)
            if parsed is not None:
                periods[col_idx] = parsed
        if len(periods) >= 2:
            return row_num, periods
    raise ValueError(
        f"Sheet {ws.title!r}: no period-header row found in first {max_scan_rows} rows"
    )


def _check_title(ws: Any, expected_substring: str) -> None:
    for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
        for cell in row:
            if isinstance(cell, str) and cell.strip().startswith("Table 11"):
                if expected_substring not in cell:
                    raise ValueError(
                        f"Sheet {ws.title!r}: expected title containing "
                        f"{expected_substring!r}, found {cell!r}"
                    )
                return
    raise ValueError(f"Sheet {ws.title!r}: no title cell found (expected 'Table 11 ...')")


def _check_anchors(seen_labels: set[str], anchors: tuple[str, ...], sheet_name: str) -> None:
    missing = [a for a in anchors if a not in seen_labels]
    if missing:
        raise ValueError(
            f"Sheet {sheet_name!r}: expected row(s) {missing} not found — layout may have changed"
        )


def _parse_single_label_sheet(
    ws: Any,
    periods: dict[int, tuple[pd.Timestamp, str]],
    header_row: int,
    table_slug: str,
    default_unit: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Tables 11-1/2/4/5: hierarchy is a single label column (B) plus leading-
    whitespace sub-items (e.g. "  of which US"). A row with a label but zero
    numeric period values is a pure section header -- it updates the running
    section/unit context but emits nothing; every other labelled row emits under
    the current section."""
    rows_out: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    section: str | None = None
    unit = default_unit

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        label = row[1] if len(row) > 1 else None
        if not isinstance(label, str) or not label.strip():
            continue
        clean_label = label.strip()
        if clean_label.startswith(("Note:", "Source:")):
            continue
        seen_labels.add(clean_label)

        values = {
            col: row[col]
            for col in periods
            if col < len(row) and _is_numeric(row[col])
        }
        if not values:
            section = _slug(clean_label)
            unit = _infer_unit(clean_label, default_unit)
            continue

        row_slug = _slug(clean_label)
        prefix = f"{table_slug}.{section}" if section else table_slug
        base_id = f"momr.{prefix}.{row_slug}"
        for col, value in values.items():
            ts, freq = periods[col]
            rows_out.append(
                {
                    "series_id": _series_id_with_freq(base_id, freq),
                    "ts": ts,
                    "value": float(value),
                    "unit": unit,
                    "freq": freq,
                }
            )

    return rows_out, seen_labels


def _parse_two_label_sheet(
    ws: Any,
    periods: dict[int, tuple[pd.Timestamp, str]],
    header_row: int,
    table_slug: str,
    default_unit: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Table 11-3 only: hierarchy is genuinely three levels deep -- a top section
    (e.g. "Closing stock levels, mb" / "Days of forward consumption... days",
    confirmed live: column B, no numeric values on that row at all) containing
    column-B sub-items (e.g. "OECD onland commercial", column B, *with* its own
    aggregate value) which in turn break down into column-C leaves (e.g.
    "Americas"). Two different top sections can share an identical column-B/C
    breadcrumb (both have an "OECD onland commercial" > "Americas" leaf, one in
    mb, one in days) -- section is tracked separately from the breadcrumb so
    those don't collide."""
    rows_out: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    context: dict[int, str] = {}
    section: str | None = None
    unit = default_unit

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        label_cols = [(1, row[1] if len(row) > 1 else None), (2, row[2] if len(row) > 2 else None)]
        populated = [
            (idx, val.strip()) for idx, val in label_cols if isinstance(val, str) and val.strip()
        ]
        if not populated:
            continue
        deepest_idx, deepest_label = populated[-1]
        if deepest_label.startswith(("Note:", "Source:")):
            continue
        seen_labels.add(deepest_label)

        values = {
            col: row[col]
            for col in periods
            if col < len(row) and _is_numeric(row[col])
        }

        if deepest_idx == 1 and not values:
            # A genuine top-level section header: column B only, no data of its
            # own (e.g. "Closing stock levels, mb"). Starts a fresh breadcrumb.
            section = _slug(deepest_label)
            unit = _infer_unit(deepest_label, default_unit)
            context = {}
            continue

        for idx, val in populated:
            context[idx] = val
        for idx in [i for i in context if i > deepest_idx]:
            del context[idx]

        if not values:
            continue

        breadcrumb = ".".join(_slug(context[i]) for i in sorted(context))
        prefix = f"{table_slug}.{section}" if section else table_slug
        base_id = f"momr.{prefix}.{breadcrumb}"
        for col, value in values.items():
            ts, freq = periods[col]
            rows_out.append(
                {
                    "series_id": _series_id_with_freq(base_id, freq),
                    "ts": ts,
                    "value": float(value),
                    "unit": unit,
                    "freq": freq,
                }
            )

    return rows_out, seen_labels


def parse_appendix(path: Path, revision_date: pd.Timestamp) -> pd.DataFrame:
    """Parses all 5 data sheets in the workbook at `path` into one ts_long-shaped
    DataFrame, `revision_date` stamped as the MOMR's own publication month (not
    ingestion time) so consecutive monthly vintages coexist rather than
    overwriting each other."""
    wb = openpyxl.load_workbook(path, data_only=True)
    frames: list[dict[str, Any]] = []

    for sheet_name, table_slug, expected_title, default_unit, anchors in _SHEETS:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Expected sheet {sheet_name!r} not found in {path.name}")
        ws = wb[sheet_name]
        _check_title(ws, expected_title)
        header_row, periods = _find_header_row(ws)

        if sheet_name in _TWO_LABEL_COLUMN_SHEETS:
            rows_out, seen_labels = _parse_two_label_sheet(
                ws, periods, header_row, table_slug, default_unit
            )
        else:
            rows_out, seen_labels = _parse_single_label_sheet(
                ws, periods, header_row, table_slug, default_unit
            )

        _check_anchors(seen_labels, anchors, sheet_name)
        frames.extend(rows_out)

    if not frames:
        raise ValueError(f"No data rows parsed from {path.name}")

    df = pd.DataFrame(frames)
    df["source"] = "opec_momr"
    df["geo"] = "WORLD"
    df["revision_date"] = revision_date
    return df[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]]
