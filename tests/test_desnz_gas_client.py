"""pipelines/desnz_gas: link discovery and both parsers. Workbooks are built here with
openpyxl, mimicking the real sheet layout; figures synthetic."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd
import pytest
from pipelines.desnz_gas.client import (
    BALANCE_COLUMNS,
    DesnzGasClient,
    discover_links,
    parse_monthly_balance,
    parse_trade,
)
from pipelines.desnz_gas.pull import balance_rows, slug, trade_rows

BASE = "https://assets.publishing.service.gov.uk/media/abc123"


def _xlsx(sheet: str, rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _balance_workbook() -> bytes:
    names = list(BALANCE_COLUMNS)
    header = ["Month", *[f"{n}\n[note 1]" for n in names], None, "M", "M", "Q", "Q", "Y"]
    jan = ["January 2026", *[float(i) for i in range(len(names))], None, "January", 1,
           "Quarter 1", 1, 2026]  # fmt: skip
    jul = ["[provisional] July 2026", *["[x]"] * len(names), None, "July", 7, "Quarter 3", 3, 2026]
    jul[1] = 5.0  # production published, everything else [x]
    return _xlsx("Month (mcm)", [["Table 4.2"], ["notes"], header, jan, jul])


def test_discover_links_finds_exactly_one_workbook_per_table() -> None:
    html = f'<a href="{BASE}/ET_4.2_SEP_26.xlsx">x</a> <a href="{BASE}/ET_4.3_SEP_26.xlsx">y</a>'

    links = discover_links(html)

    assert links == {"4.2": f"{BASE}/ET_4.2_SEP_26.xlsx", "4.3": f"{BASE}/ET_4.3_SEP_26.xlsx"}


def test_a_missing_or_ambiguous_link_fails_loudly() -> None:
    with pytest.raises(ValueError, match=r"ET 4\.3"):
        discover_links(f'<a href="{BASE}/ET_4.2_SEP_26.xlsx">')
    two = f"{BASE}/ET_4.2_SEP_26.xlsx {BASE}/ET_4.2_AUG_26.xlsx {BASE}/ET_4.3_SEP_26.xlsx"
    with pytest.raises(ValueError, match=r"ET 4\.2"):
        discover_links(two)


def test_monthly_balance_reads_months_from_the_number_columns_and_skips_x() -> None:
    frame = parse_monthly_balance(_balance_workbook())

    july = frame[frame["ts"] == pd.Timestamp("2026-07-01")]
    assert list(july["line"]) == ["production"]  # every [x] cell gave no row
    assert july["provisional"].all()
    jan = frame[frame["ts"] == pd.Timestamp("2026-01-01")].set_index("line")["value"]
    assert jan["production"] == 0.0 and jan["demand"] == float(len(BALANCE_COLUMNS) - 1)


def test_a_renamed_column_fails_loudly() -> None:
    content = _xlsx("Month (mcm)", [["Month", "Gross production", "M", "Y"]])

    with pytest.raises(ValueError, match="columns not found"):
        parse_monthly_balance(content)


def test_trade_flat_rows_parse_with_flow_names() -> None:
    header = [
        "Month",
        "Year",
        "M",
        "Q",
        "Import/export",
        "Type",
        "Country",
        "Pipeline",
        "GWh",
        "mcm",
    ]
    rows = [
        header,
        ["July", 2026, 7, 3, "Import", "Pipeline", "Norway", "Langeled to Easington", 1, 100.0],
        ["July", 2026, 7, 3, "Export", "Pipeline", "Belgium", "Interconnector UK (IUK)", 1, 40.0],
        ["July", 2026, 7, 3, "Net Import", "Net imports", "Net imports", "NA", 1, 60.0],
    ]

    trade = parse_trade(_xlsx("Data in flat format", rows))

    assert list(trade["flow"]) == ["imports", "exports", "net"]
    ids = set(trade_rows(trade, pd.Timestamp("2026-10-26"))["series_id"])
    assert "desnz.gas.imports.pipeline.norway.langeled_to_easington.gb" in ids


def test_provisional_months_are_flagged_in_their_own_series() -> None:
    rows = balance_rows(parse_monthly_balance(_balance_workbook()), pd.Timestamp("2026-10-26"))

    flags = rows[rows["series_id"] == "desnz.gas.provisional.gb"]
    assert list(flags["ts"]) == [pd.Timestamp("2026-07-01")]
    assert slug("Trinidad & Tobago") == "trinidad_tobago"


@pytest.mark.vcr
def test_live_page_links_to_the_current_workbooks() -> None:
    links = DesnzGasClient().links()

    assert set(links) == {"4.2", "4.3"}
    assert all(url.endswith(".xlsx") for url in links.values())
