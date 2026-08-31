from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.opec_momr.parser import parse_appendix

FIXTURE_PATH = Path("tests/fixtures/opec_momr/momr-appendix-august-2026.xlsx")
REVISION_DATE = pd.Timestamp("2026-08-01")


def test_parse_appendix_returns_ts_long_conformant_dataframe() -> None:
    df = parse_appendix(FIXTURE_PATH, REVISION_DATE)

    validate_ts_long(df)  # raises on schema mismatch
    assert not df.empty
    # Full-breadth capture, not a curated handful -- confirmed live this real
    # file yields 400+ distinct series across the 5 sheets.
    assert df["series_id"].nunique() > 300
    assert (df["revision_date"] == REVISION_DATE).all()
    assert (df["geo"] == "WORLD").all()
    assert not df.duplicated(subset=["series_id", "ts"]).any()


def test_world_demand_matches_known_headline_value() -> None:
    # Acceptance criterion: latest MOMR world-demand number matches the PDF
    # headline -- confirmed live against the real August 2026 MOMR (2026 annual
    # world demand forecast).
    df = parse_appendix(FIXTURE_PATH, REVISION_DATE)

    series_id = "momr.demand_balance.world_demand.a_total_world_demand.annual"
    row = df[(df["series_id"] == series_id) & (df["ts"] == pd.Timestamp("2026-01-01"))]

    assert len(row) == 1
    assert row.iloc[0]["value"] == pytest.approx(105.739323, abs=1e-4)
    assert row.iloc[0]["unit"] == "mb/d"


def test_oil_on_water_and_regional_stocks_captured() -> None:
    # The freight-adjacent pieces -- oil-on-water and OECD stocks by region.
    df = parse_appendix(FIXTURE_PATH, REVISION_DATE)

    assert (df["series_id"].str.contains("oilonwater")).any()
    is_oecd_stocks = df["series_id"].str.contains("oecd_stocks")
    is_americas = df["series_id"].str.contains("americas")
    assert (is_oecd_stocks & is_americas).any()


def test_rig_count_monthly_column_captured() -> None:
    # Table 11-5 has real datetime columns (the latest 1-2 actual months) amid
    # otherwise annual/quarterly columns -- confirmed live.
    df = parse_appendix(FIXTURE_PATH, REVISION_DATE)

    monthly_rigs = df[(df["series_id"] == "momr.rig_count.us.monthly")]
    assert not monthly_rigs.empty
    assert (monthly_rigs["freq"] == "M").all()


def test_renamed_anchor_row_raises_value_error(tmp_path: Path) -> None:
    # Fail-loudly layout-drift guard: since every row is captured generically
    # (no curated subset), a renamed/missing anchor row is the actual signal
    # that OPEC changed the sheet layout.
    corrupted_path = tmp_path / "corrupted.xlsx"
    wb = openpyxl.load_workbook(FIXTURE_PATH)
    ws = wb["Table 11 - 1"]
    for row in ws.iter_rows():
        if row[1].value == "(a) Total world demand":
            row[1].value = "Renamed row"
            break
    wb.save(corrupted_path)

    with pytest.raises(ValueError, match="layout may have changed"):
        parse_appendix(corrupted_path, REVISION_DATE)


def test_wrong_sheet_title_raises_value_error(tmp_path: Path) -> None:
    corrupted_path = tmp_path / "corrupted_title.xlsx"
    wb = openpyxl.load_workbook(FIXTURE_PATH)
    ws = wb["Table 11 - 1"]
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("Table 11 - 1"):
                cell.value = "Table 11 - 1: Something completely different"
                break
    wb.save(corrupted_path)

    with pytest.raises(ValueError, match="expected title containing"):
        parse_appendix(corrupted_path, REVISION_DATE)
