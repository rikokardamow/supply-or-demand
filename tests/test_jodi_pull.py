from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.jodi.pull_jodi import filter_and_transform

REVISION_DATE = datetime(2026, 8, 1, tzinfo=UTC)


def _raw_row(
    ref_area: str, flow: str, unit: str, value: str, period: str = "2026-06"
) -> dict[str, str]:
    return {
        "REF_AREA": ref_area,
        "TIME_PERIOD": period,
        "ENERGY_PRODUCT": "CRUDEOIL",
        "FLOW_BREAKDOWN": flow,
        "UNIT_MEASURE": unit,
        "OBS_VALUE": value,
        "ASSESSMENT_CODE": "3",
    }


def test_filter_and_transform_returns_ts_long_conformant_dataframe() -> None:
    raw = pd.DataFrame(
        [
            _raw_row("US", "INDPROD", "KBD", "13818.0000"),
            _raw_row("US", "INDPROD", "KBBL", "-"),  # wrong unit for this flow -- dropped
            _raw_row("US", "REFINOBS", "KBD", "16000.0000"),
            _raw_row("US", "CLOSTLV", "KBBL", "450000.0000"),
        ]
    )

    df = filter_and_transform(raw, REVISION_DATE)

    validate_ts_long(df)  # raises on schema mismatch
    assert len(df) == 3
    assert set(df["series_id"]) == {
        "jodi.crude_production.us",
        "jodi.refinery_intake.us",
        "jodi.closing_stocks.us",
    }
    assert (df["geo"] == "US").all()


def test_filter_and_transform_drops_missing_and_confidential_markers() -> None:
    raw = pd.DataFrame(
        [
            _raw_row("US", "INDPROD", "KBD", "13818.0000"),
            _raw_row("SA", "INDPROD", "KBD", "-"),  # not reported
            _raw_row("AE", "INDPROD", "KBD", "x"),  # confidential/not applicable
        ]
    )

    df = filter_and_transform(raw, REVISION_DATE)

    assert len(df) == 1
    assert df.iloc[0]["geo"] == "US"


def test_filter_and_transform_excludes_countries_outside_top_15() -> None:
    raw = pd.DataFrame(
        [
            _raw_row("US", "INDPROD", "KBD", "13818.0000"),
            _raw_row("XX", "INDPROD", "KBD", "500.0000"),  # not in TOP_15_PRODUCERS
        ]
    )

    df = filter_and_transform(raw, REVISION_DATE)

    assert list(df["geo"]) == ["US"]


def test_filter_and_transform_excludes_non_crude_products() -> None:
    row = _raw_row("US", "INDPROD", "KBD", "13818.0000")
    other_product = {**row, "ENERGY_PRODUCT": "NGL"}
    raw = pd.DataFrame([row, other_product])

    df = filter_and_transform(raw, REVISION_DATE)

    assert len(df) == 1


def test_filter_and_transform_returns_empty_frame_when_nothing_matches() -> None:
    raw = pd.DataFrame([_raw_row("XX", "INDPROD", "KBD", "500.0000")])

    df = filter_and_transform(raw, REVISION_DATE)

    assert df.empty
    assert list(df.columns) == [
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date",
    ]  # fmt: skip
