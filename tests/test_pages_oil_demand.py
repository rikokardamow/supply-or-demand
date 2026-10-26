"""`apps/dashboard/pages/23_oil_demand.py`, driven through AppTest against an isolated
lake -- the same mechanism as tests/test_pages_curve_window.py. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).parent.parent
APP_ENTRYPOINT = REPO_ROOT / "apps" / "dashboard" / "app.py"
REVISION = pd.Timestamp("2026-10-10")
_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _seed(storage, china_follows_gdp: bool = True) -> None:
    rng = np.random.default_rng(5)
    quarters = pd.date_range("2012-01-01", periods=58, freq="QS")
    months = pd.date_range("2012-01-01", periods=58 * 3, freq="MS")
    for geo in ("US", "CN", "EA"):
        gdp = pd.Series(2.0 + rng.normal(0, 2.0, 58), index=quarters)
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": f"oecd.gdp_real_yoy.{geo.lower()}", "source": "oecd",
                    "ts": quarters, "value": gdp.to_numpy(), "unit": "% y/y", "geo": geo,
                    "freq": "Q", "revision_date": REVISION,
                }
            )[_COLUMNS],
            source="oecd",
        )  # fmt: skip
        members = [geo] if geo != "EA" else list(od.EURO_AREA_BASKET)
        follows = china_follows_gdp or geo != "CN"
        # Demand level whose y/y growth is 1.5 x GDP growth (or pure noise for China).
        growth = 1.5 * gdp if follows else pd.Series(rng.normal(0, 5.0, 58), index=quarters)
        level = pd.Series(1000.0, index=quarters)
        for i in range(4, 58):
            level.iloc[i] = level.iloc[i - 4] * (1 + growth.iloc[i] / 100)
        monthly = level.reindex(months, method="ffill")
        for member in members:
            storage.write_ts_long(
                pd.DataFrame(
                    {
                        "series_id": f"jodi.total_demand.{member.lower()}", "source": "jodi",
                        "ts": months, "value": monthly.to_numpy(), "unit": "kb/d",
                        "geo": member, "freq": "M", "revision_date": REVISION,
                    }
                )[_COLUMNS],
                source="jodi",
            )  # fmt: skip


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/23_oil_demand.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info] + [e.value for e in at.warning]
    for table in at.dataframe:
        parts.append(table.value.to_string())
    return " ".join(str(part) for part in parts)


def test_an_empty_lake_renders_a_no_data_message_naming_the_command(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines.jodi.pull_demand" in said


def test_both_fits_are_shown_side_by_side_for_every_block(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "Full panel" in said
    assert "Ex-pandemic" in said
    for label in od.BLOCK_LABELS.values():
        assert label in said, label
    assert "ex Malta" in said


def test_an_insignificant_slope_is_called_insignificant_in_words(isolated_lake) -> None:
    _seed(isolated_lake, china_follows_gdp=False)

    said = _said(_run_page())

    assert "not statistically significant" in said


def test_a_scenario_series_is_named_as_an_assumption(isolated_lake, tmp_path, monkeypatch) -> None:
    from pipelines.derived import oil_demand as derived

    csv = tmp_path / "gdp_assumptions.csv"
    csv.write_text(
        "block,quarter,gdp_yoy_pct,author,as_of\nus,2027-01-01,1.0,Test Author,2026-10-01\n"
    )
    monkeypatch.setattr(derived, "ASSUMPTIONS_PATH", csv)
    _seed(isolated_lake)
    isolated_lake.write_ts_long(
        pd.DataFrame(
            {
                "series_id": "derived.oil_demand.us.yoy.scenario", "source": "derived",
                "ts": [pd.Timestamp("2027-01-01")], "value": [1.2], "unit": "% y/y",
                "geo": "US", "freq": "Q", "revision_date": REVISION,
            }
        )[_COLUMNS],
        source="derived",
    )  # fmt: skip

    said = _said(_run_page())

    assert "assumption" in said.lower()
    assert "not a forecast" in said.lower()
    assert "Test Author" in said and "2026-10-01" in said


def test_the_model_card_states_the_benchmark_and_the_pandemic_window(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert od.BENCHMARK in said
    assert "2020-Q1" in said and "2021-Q4" in said
