from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.opec_momr.pdf_parser import find_issue_month, parse_doc_crude_secondary

FIXTURE_PATH = Path("tests/fixtures/opec_momr/momr-august-2026.pdf")


def test_find_issue_month_reads_the_real_publication_date() -> None:
    assert find_issue_month(FIXTURE_PATH) == pd.Timestamp("2026-08-01")


def test_parse_doc_crude_secondary_returns_ts_long_conformant_dataframe() -> None:
    df = parse_doc_crude_secondary(FIXTURE_PATH, pd.Timestamp("2026-08-01"))

    validate_ts_long(df)  # raises on schema mismatch
    assert not df.empty
    assert df["geo"].nunique() >= 20  # every DoC country, not a curated subset
    assert not df.duplicated(subset=["series_id", "ts"]).any()
    assert (df["unit"] == "tb/d").all()


def test_saudi_arabia_matches_known_pdf_value() -> None:
    # Confirmed live against the real August 2026 MOMR's own printed table.
    df = parse_doc_crude_secondary(FIXTURE_PATH, pd.Timestamp("2026-08-01"))

    row = df[
        (df["series_id"] == "momr.doc_crude_secondary.saudi_arabia.monthly")
        & (df["ts"] == pd.Timestamp("2026-07-01"))
    ]
    assert len(row) == 1
    assert row.iloc[0]["value"] == pytest.approx(7352.0)


def test_opec_total_cross_checks_against_sum_of_members() -> None:
    # OPEC's own "Total OPEC" line for July 2026 was 23,632 tb/d -- summing
    # every individual member row this parser extracted should land within
    # OPEC's own "totals may not add up due to independent rounding" tolerance.
    df = parse_doc_crude_secondary(FIXTURE_PATH, pd.Timestamp("2026-08-01"))

    opec_members = [
        "Algeria", "Congo", "Equatorial Guinea", "Gabon", "IR Iran", "Iraq",
        "Kuwait", "Libya", "Nigeria", "Saudi Arabia", "UAE", "Venezuela",
    ]  # fmt: skip
    july = df[(df["ts"] == pd.Timestamp("2026-07-01")) & (df["geo"].isin(opec_members))]
    assert july["value"].sum() == pytest.approx(23632, abs=2)


def test_missing_table_raises_value_error(tmp_path: Path) -> None:
    blank_pdf = tmp_path / "blank.pdf"
    # A minimal valid PDF with no MOMR content at all.
    blank_pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>"
    )

    with pytest.raises(ValueError, match="not found in this PDF"):
        parse_doc_crude_secondary(blank_pdf, pd.Timestamp("2026-08-01"))
