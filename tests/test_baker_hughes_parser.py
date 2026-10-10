from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.baker_hughes.parser import parse_weekly_rig_counts

REVISION_DATE = pd.Timestamp("2026-08-31")

_HEADER = [
    "Country", "County", "Basin", "GOM", "DrillFor", "Location",
    "State/Province", "Trajectory", "Year", "Month", "US_PublishDate", "Rig Count Value",
]  # fmt: skip

_SAMPLE_ROWS = [
    # Country, County, Basin, GOM, DrillFor, Location, State, Trajectory, Year, Month, Date, Value
    [
        "UNITED STATES",
        "Midland",
        "Permian",
        "No",
        "Oil",
        "Land",
        "TEXAS",
        "Horizontal",
        2026,
        8,
        "2026-08-28",
        250,
    ],  # noqa: E501
    [
        "UNITED STATES",
        "Reeves",
        "Permian",
        "No",
        "Oil",
        "Land",
        "TEXAS",
        "Horizontal",
        2026,
        8,
        "2026-08-28",
        100,
    ],  # noqa: E501
    [
        "UNITED STATES",
        "Weld",
        "DJ-Niobrara",
        "No",
        "Gas",
        "Land",
        "COLORADO",
        "Horizontal",
        2026,
        8,
        "2026-08-28",
        5,
    ],  # noqa: E501
    [
        "CANADA",
        "Central Alberta",
        "Other",
        "No",
        "Oil",
        "Land",
        "ALBERTA",
        "Horizontal",
        2026,
        8,
        "2026-08-28",
        30,
    ],  # noqa: E501
]


def _build_workbook(path: Path, header: list[str] | None = None, blank_rows: int = 10) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NAM Weekly"
    for _ in range(blank_rows):
        ws.append([None])
    ws.append(header if header is not None else _HEADER)
    for row in _SAMPLE_ROWS:
        ws.append(row)
    wb.save(path)


def test_parse_weekly_rig_counts_returns_ts_long_conformant_dataframe(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    _build_workbook(path)

    df = parse_weekly_rig_counts(str(path), REVISION_DATE)

    validate_ts_long(df)  # raises on schema mismatch
    assert not df.empty
    assert not df.duplicated(subset=["series_id", "ts"]).any()
    assert (df["unit"] == "rigs").all()
    assert (df["freq"] == "W").all()


def test_country_total_sums_across_drillfor_and_state(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    _build_workbook(path)

    df = parse_weekly_rig_counts(str(path), REVISION_DATE)

    us_total = df[df["series_id"] == "bh.rigs.united_states.total"]
    assert len(us_total) == 1
    assert us_total.iloc[0]["value"] == 250 + 100 + 5  # both TX oil rows + the CO gas row


def test_country_drillfor_aggregate_sums_across_states(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    _build_workbook(path)

    df = parse_weekly_rig_counts(str(path), REVISION_DATE)

    us_oil = df[df["series_id"] == "bh.rigs.united_states.oil"]
    assert len(us_oil) == 1
    assert us_oil.iloc[0]["value"] == 250 + 100  # Midland + Reeves, both TX oil


def test_state_level_series_present_and_correct(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    _build_workbook(path)

    df = parse_weekly_rig_counts(str(path), REVISION_DATE)

    tx_oil = df[df["series_id"] == "bh.rigs.united_states.oil.texas"]
    assert len(tx_oil) == 1
    assert tx_oil.iloc[0]["value"] == 350
    assert tx_oil.iloc[0]["geo"] == "TEXAS"


def test_wrong_header_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    mangled_header = [*_HEADER[:-1], "Renamed Column"]
    _build_workbook(path, header=mangled_header)

    with pytest.raises(ValueError, match="doesn't match the expected columns"):
        parse_weekly_rig_counts(str(path), REVISION_DATE)


def test_missing_sheet_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "rigs.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Some Other Sheet"
    wb.save(path)

    with pytest.raises(ValueError, match="not found"):
        parse_weekly_rig_counts(str(path), REVISION_DATE)
