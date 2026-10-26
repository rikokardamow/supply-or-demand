# tests/test_oecd_pull.py
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.oecd.pull_gdp import AREA_GEO, to_ts_long

REVISION_DATE = datetime(2026, 10, 10, tzinfo=UTC)


def test_area_codes_map_to_the_lakes_geo_codes() -> None:
    assert AREA_GEO == {"USA": "US", "CHN": "CN", "EA": "EA"}


def test_to_ts_long_stamps_the_quarter_start_and_the_real_yoy_unit() -> None:
    raw = pd.DataFrame(
        {
            "REF_AREA": ["CHN", "CHN", "EA"],
            "TIME_PERIOD": ["2026-Q1", "2026-Q2", "2025-Q4"],
            "OBS_VALUE": [5.0, 4.3, 1.2],
            "OBS_STATUS": ["A", "A", "A"],
        }
    )

    df = to_ts_long(raw, REVISION_DATE)

    validate_ts_long(df)
    cn = df[df["series_id"] == "oecd.gdp_real_yoy.cn"].sort_values("ts")
    assert cn["ts"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")]
    assert cn["value"].tolist() == [5.0, 4.3]
    ea = df[df["series_id"] == "oecd.gdp_real_yoy.ea"].iloc[0]
    assert ea["ts"] == pd.Timestamp("2025-10-01")
    assert ea["geo"] == "EA"
    assert (df["unit"] == "% y/y").all()
    assert (df["freq"] == "Q").all()
    assert (df["source"] == "oecd").all()
