"""pipelines/carbon: EEX and registry parsers on workbooks built here (figures synthetic),
plus live link discovery and the EEX 404 rule from cassettes."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd
import pytest
from pipelines.carbon.client import (
    CarbonClient,
    discover_registry_link,
    parse_eex,
    parse_registry,
    sector_of,
)
from pipelines.carbon.pull import eex_rows, registry_rows

AT = pd.Timestamp("2026-10-26")


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        assert ws is not None
        ws.title, first = name, False
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


EEX_HEADER = [None, "Date", "Time", "Auction Name", "Contract", "Status", "Auction Price €/tCO2",
              "Auction Volume tCO2", "Total Amount of Bids", "Cover Ratio",
              "Total Number of Bidders", "Total Revenue €"]  # fmt: skip


def _eex() -> bytes:
    rows = [
        [None, "EEX Emissions market / Primary Market Auction"],
        [None, "References", None, None, None, None, "Prices"],
        EEX_HEADER,
        [None, pd.Timestamp("2026-10-26"), "11:00", "Auction 4. Period CAP3 EU", "T3PA",
         "successful", 80.0, 1000.0, 1600.0, 1.6, 20, 80000.0],
        [None, pd.Timestamp("2026-10-23"), "11:00", "Auction 4. Period DE", "T3PA",
         "cancelled", None, 900.0, 800.0, 0.89, 12, None],
        [None, pd.Timestamp("2024-03-01"), "11:00", "EUAA Auction CAP3 PL", "EAA3",
         "successful", 60.0, 500.0, 700.0, 1.4, 10, 30000.0],
    ]  # fmt: skip
    return _xlsx({"EU ETS1": rows})


def test_eex_parse_finds_the_header_whatever_its_column() -> None:
    auctions = parse_eex(_eex())

    assert len(auctions) == 3
    assert auctions.loc[0, "price"] == 80.0 and auctions.loc[0, "cover_ratio"] == 1.6
    assert pd.isna(auctions.loc[1, "price"])


def test_a_cancelled_auction_gives_a_flag_and_no_price() -> None:
    rows = eex_rows(parse_eex(_eex()), AT)

    prices = rows[rows["series_id"] == "eex.eua.auction.price"]
    assert list(prices["ts"]) == [pd.Timestamp("2026-10-26")]
    assert "eex.eua.auction.cancelled" in set(rows["series_id"])
    assert "eex.euaa.auction.price" in set(rows["series_id"])


def _registry() -> bytes:
    header = ["REGISTRY_CODE", "MAIN_ACTIVITY_TYPE_CODE", "ALLOCATION_2024",
              "ALLOCATION_RESERVE_2024", "ALLOCATION_TRANSITIONAL_2024", "ALLOCATION_FEETS_2024",
              "CH_ALLOCATION_2024", "VERIFIED_EMISSIONS_2024", "CH_VERIFIED_EMISSIONS_2024",
              "ALLOCATION2008", "VERIFIED_EMISSIONS_2008"]  # fmt: skip
    rows = [
        ["Please see Read Me"], [], header,
        ["DE", "20", "100", "10", "5", "7", "99", "300", "88", "1", "2"],
        ["DE", "29", "50", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a"],
        ["FR", "10", "n/a", "n/a", "n/a", "n/a", "n/a", "40", "n/a", "n/a", "n/a"],
        ["IT", "50", "n/a", "n/a", "n/a", "n/a", "n/a", "Excluded", "n/a", "n/a", "n/a"],
    ]  # fmt: skip
    return _xlsx({"data": rows})


def test_registry_totals_by_sector_with_n_a_not_zero_and_swiss_left_out() -> None:
    totals = parse_registry(_registry())
    get = totals.set_index(["registry", "sector", "year", "metric"])["value"]

    assert get[("DE", "combustion", 2024, "free_allocation")] == 115.0  # 100 + 10 + 5
    assert get[("DE", "combustion", 2024, "verified_emissions")] == 300.0  # CH 88 not added
    assert get[("DE", "combustion", 2024, "allocation_feets")] == 7.0
    assert ("DE", "industry", 2024, "verified_emissions") not in get.index  # n/a is not 0
    assert get[("DE", "industry", 2024, "free_allocation")] == 50.0
    assert get[("FR", "aviation", 2024, "reporting")] == 1.0
    assert ("IT", "maritime", 2024, "reporting") not in get.index  # Excluded is not a report
    assert get[("DE", "combustion", 2008, "verified_emissions")] == 2.0  # no-underscore 2008


def test_sector_codes_and_registry_rows() -> None:
    assert [sector_of(c) for c in ("1", "20", "10", "50", "29", "x")] == [
        "combustion",
        "combustion",
        "aviation",
        "maritime",
        "industry",
        "unknown",
    ]
    rows = registry_rows(parse_registry(_registry()), AT)
    assert "eu_ets.verified_emissions.combustion.de" in set(rows["series_id"])
    assert set(rows["freq"]) == {"A"}


def test_registry_link_picks_the_newest_year() -> None:
    html = (
        '<a href="/document/download/aaa_en?filename=verified_emissions_2024_en.xlsx">'
        '<a href="/document/download/bbb_en?filename=verified_emissions_2025_en.xlsx">'
    )

    year, url = discover_registry_link(html)

    assert year == 2025
    assert (
        url
        == "https://climate.ec.europa.eu/document/download/bbb_en?filename=verified_emissions_2025_en.xlsx"
    )
    with pytest.raises(ValueError, match="no verified_emissions"):
        discover_registry_link("<html></html>")


@pytest.mark.vcr
def test_live_registry_page_links_a_verified_emissions_file() -> None:
    year, url = CarbonClient().registry_link()

    assert year >= 2025 and url.endswith(f"verified_emissions_{year}_en.xlsx")


@pytest.mark.vcr
def test_an_unpublished_eex_year_is_none_not_an_error() -> None:
    assert CarbonClient().eex_report(2019) is None
