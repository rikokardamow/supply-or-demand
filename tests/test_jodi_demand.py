from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.jodi.pull_demand import (
    DEMAND_COUNTRIES,
    EURO_AREA_20,
    filter_and_transform,
)

REVISION_DATE = datetime(2026, 10, 10, tzinfo=UTC)


def _row(
    ref_area: str,
    value: str,
    period: str = "2026-06",
    flow: str = "TOTDEMO",
    product: str = "TOTPRODS",
    unit: str = "KBD",
) -> dict[str, str]:
    return {
        "REF_AREA": ref_area,
        "TIME_PERIOD": period,
        "ENERGY_PRODUCT": product,
        "FLOW_BREAKDOWN": flow,
        "UNIT_MEASURE": unit,
        "OBS_VALUE": value,
        "ASSESSMENT_CODE": "3",
    }


def test_the_country_list_is_the_three_blocks() -> None:
    assert len(EURO_AREA_20) == 20
    assert len(set(EURO_AREA_20)) == 20
    assert ["US", "CN", *EURO_AREA_20] == DEMAND_COUNTRIES


def test_filter_and_transform_keeps_total_product_demand_in_kbd_only() -> None:
    raw = pd.DataFrame(
        [
            _row("US", "20000.0000"),
            _row("US", "9000.0000", product="GASOLINE"),  # one product, not the total
            _row("US", "600000.0000", unit="KBBL"),  # a volume, not a rate
            _row("US", "17000.0000", flow="REFGROUT"),  # refinery output, not demand
            _row("CN", "14000.0000"),
            _row("DE", "2000.0000"),
            _row("RU", "3500.0000"),  # not one of the three blocks
        ]
    )

    df = filter_and_transform(raw, REVISION_DATE)

    validate_ts_long(df)
    assert set(df["series_id"]) == {
        "jodi.total_demand.us",
        "jodi.total_demand.cn",
        "jodi.total_demand.de",
    }
    assert (df["unit"] == "kb/d").all()
    assert (df["freq"] == "M").all()
    assert (df["source"] == "jodi").all()
    us = df[df["series_id"] == "jodi.total_demand.us"].iloc[0]
    assert us["value"] == 20000.0
    assert us["ts"] == pd.Timestamp("2026-06-01")
    assert us["geo"] == "US"


def test_filter_and_transform_drops_not_reported_markers_rather_than_zeroing_them() -> None:
    """`-` is "not reported". Written as 0.0 it would read as a country consuming no oil."""
    raw = pd.DataFrame([_row("HR", "-"), _row("MT", "x"), _row("GR", "250.0000")])

    df = filter_and_transform(raw, REVISION_DATE)

    assert list(df["series_id"]) == ["jodi.total_demand.gr"]


def test_filter_and_transform_returns_an_empty_conformant_frame_when_nothing_matches() -> None:
    df = filter_and_transform(pd.DataFrame([_row("RU", "3500.0000")]), REVISION_DATE)

    assert df.empty
    assert list(df.columns) == [
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
    ]  # fmt: skip
