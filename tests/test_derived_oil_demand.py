# tests/test_derived_oil_demand.py
"""pipelines/derived/oil_demand.py. Every figure is SYNTHETIC -- see
tests/test_core_oil_demand.py for why."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od
from core.schemas import validate_ts_long
from pipelines.derived import oil_demand as derived

REVISION = pd.Timestamp("2026-10-10")


def _monthly(months: int = 15 * 12) -> pd.DataFrame:
    """Every basket member at a flat level, the US growing 2 % a year, China flat."""
    index = pd.date_range("2012-01-01", periods=months, freq="MS")
    frame = pd.DataFrame(100.0, index=index, columns=list(od.EURO_AREA_BASKET))
    frame["MT"] = 1.0
    frame["CN"] = 14000.0
    frame["US"] = 20000.0 * (1.02 ** ((index.year - 2012) + (index.month - 1) / 12))
    return frame


def _gdp(value: float = 2.0, quarters: int = 58) -> pd.Series:
    index = pd.date_range("2012-01-01", periods=quarters, freq="QS")
    return pd.Series(value + np.sin(np.arange(quarters)), index=index)


def _assumptions(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "block": [row[0] for row in rows],
            "quarter": pd.to_datetime([row[1] for row in rows]),
            "gdp_yoy_pct": pd.to_numeric([row[2] for row in rows], errors="coerce"),
            "author": "test",
            "as_of": "2026-10-10",
        }
    )


def _gdp_by_block() -> dict[str, pd.Series]:
    return {block: _gdp() for block in od.BLOCKS}


def test_build_panel_uses_the_blocks_basket_and_ignores_malta() -> None:
    monthly = _monthly()
    monthly.loc["2015-09-01":"2016-01-01", "MT"] = np.nan  # Malta's real gap

    panel = derived.build_panel("ea", monthly, _gdp())

    assert panel.index.min() == pd.Timestamp("2013-01-01")
    assert len(panel) == 54, "Malta's gap must not cost the euro area a single quarter"


def test_build_rows_writes_conformant_level_and_yoy_series_per_block() -> None:
    rows = derived.build_rows(_monthly(), _gdp_by_block(), _assumptions([]), REVISION)

    validate_ts_long(rows)
    assert set(rows["series_id"]) == {
        f"derived.oil_demand.{block}.{kind}" for block in od.BLOCKS for kind in ("level", "yoy")
    }
    assert (rows["source"] == "derived").all()
    assert (rows["freq"] == "Q").all()
    assert rows["value"].notna().all(), "NaN quarters are not written"
    level = rows[rows["series_id"] == "derived.oil_demand.ea.level"]
    assert (level["unit"] == "kb/d").all()
    assert level["value"].iloc[0] == pytest.approx(1900.0)  # 19 members x 100
    assert (level["geo"] == "EA").all()
    yoy = rows[rows["series_id"] == "derived.oil_demand.us.yoy"]
    assert (yoy["unit"] == "% y/y").all()
    assert yoy["value"].iloc[0] == pytest.approx(2.0, abs=0.01)
    assert yoy["ts"].min() == pd.Timestamp("2013-01-01")


def test_an_incomplete_latest_quarter_writes_no_row() -> None:
    """Live today: the latest month is missing Croatia and Greece. The quarter must be
    absent from the lake, not present and understated."""
    monthly = _monthly()
    last_quarter = monthly.index.max() - pd.offsets.QuarterBegin(startingMonth=1)
    monthly.loc[monthly.index.max(), "HR"] = np.nan

    rows = derived.build_rows(monthly, _gdp_by_block(), _assumptions([]), REVISION)

    ea_level = rows[rows["series_id"] == "derived.oil_demand.ea.level"]
    assert ea_level["ts"].max() < last_quarter
    us_level = rows[rows["series_id"] == "derived.oil_demand.us.level"]
    assert us_level["ts"].max() == last_quarter, "one block's gap must not blank another"


def test_assumed_gdp_growth_writes_a_scenario_series_and_nothing_else() -> None:
    assumptions = _assumptions([("us", "2027-01-01", "2.0"), ("us", "2027-04-01", "1.0")])

    rows = derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)

    scenario = rows[rows["series_id"].str.endswith(".scenario")]
    assert set(scenario["series_id"]) == {"derived.oil_demand.us.yoy.scenario"}
    assert scenario["ts"].tolist() == [pd.Timestamp("2027-01-01"), pd.Timestamp("2027-04-01")]
    observed = rows[rows["series_id"] == "derived.oil_demand.us.yoy"]
    assert observed["ts"].max() < pd.Timestamp("2027-01-01"), (
        "an assumption-driven value must never land under the observed id"
    )


def test_a_blank_assumption_writes_no_scenario_row() -> None:
    assumptions = _assumptions([("us", "2027-01-01", ""), ("us", "2027-04-01", "1.0")])

    rows = derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)

    scenario = rows[rows["series_id"].str.endswith(".scenario")]
    assert scenario["ts"].tolist() == [pd.Timestamp("2027-04-01")]


def test_an_assumption_for_an_unknown_block_raises() -> None:
    assumptions = _assumptions([("row", "2027-01-01", "3.0")])

    with pytest.raises(ValueError, match="row"):
        derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)


def test_an_assumption_for_a_quarter_already_observed_raises() -> None:
    """A scenario row dated inside history would sit beside a measurement of the same
    quarter. Refuse it: the file's author meant a future quarter and mistyped."""
    assumptions = _assumptions([("us", "2024-01-01", "2.0")])

    with pytest.raises(ValueError, match="already observed"):
        derived.build_rows(_monthly(), _gdp_by_block(), assumptions, REVISION)


def test_read_assumptions_parses_the_committed_file() -> None:
    frame = derived.read_assumptions(derived.ASSUMPTIONS_PATH)

    assert list(frame.columns) == ["block", "quarter", "gdp_yoy_pct", "author", "as_of"]
    assert set(frame["block"]) <= set(od.BLOCKS)
    assert pd.api.types.is_datetime64_any_dtype(frame["quarter"])


def test_main_reads_and_writes_an_isolated_lake(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    monthly = _monthly()
    long = monthly.reset_index(names="ts").melt(id_vars="ts", var_name="geo", value_name="value")
    storage.write_ts_long(
        long.assign(
            series_id="jodi.total_demand." + long["geo"].str.lower(),
            source="jodi", unit="kb/d", freq="M", revision_date=REVISION,
        )[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]],
        source="jodi",
    )  # fmt: skip
    for geo in ("US", "CN", "EA"):
        gdp = _gdp()
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": f"oecd.gdp_real_yoy.{geo.lower()}",
                    "source": "oecd", "ts": gdp.index, "value": gdp.to_numpy(),
                    "unit": "% y/y", "geo": geo, "freq": "Q", "revision_date": REVISION,
                }
            ),
            source="oecd",
        )  # fmt: skip

    derived.main()

    written = storage.read_ts_long(series_prefix="derived.oil_demand.", source="derived")
    assert "derived.oil_demand.cn.yoy" in set(written["series_id"])


def test_main_fails_loudly_when_the_demand_series_are_absent(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")

    with pytest.raises(RuntimeError, match=r"pipelines\.jodi\.pull_demand"):
        derived.main()
