"""`apps/dashboard/pages/24_rin.py`, driven through AppTest against an isolated lake -- the
same mechanism as tests/test_pages_oil_demand.py. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
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


def _rows(series_id: str, source: str, months: list[str], value: float, unit: str):
    return pd.DataFrame(
        {
            "series_id": series_id, "source": source, "ts": pd.to_datetime(months),
            "value": value, "unit": unit, "geo": "US", "freq": "M", "revision_date": REVISION,
        }
    )[_COLUMNS]  # fmt: skip


def _seed(storage, forward_status: str = "final") -> None:
    observed = ["2026-05-01", "2026-06-01", "2026-07-01"]
    projected = ["2026-08-01", "2026-09-01"]
    for category in ("cellulosic", "biomass_based_diesel", "advanced", "total"):
        storage.write_ts_long(
            pd.concat(
                [
                    _rows(f"derived.rin.mandate.{category}.observed.final", "derived",
                          observed, 2.0, "billion RINs"),
                    _rows(f"derived.rin.mandate.{category}.projected.{forward_status}",
                          "derived", projected, 2.1, "billion RINs"),
                ]
            ),
            source="derived",
        )  # fmt: skip
    for code in ("mgtcpusx_p", "dftcpus_p"):
        storage.write_ts_long(
            pd.concat(
                [
                    _rows(f"steo.{code}.observed", "eia_steo", observed, 5.0, "mb/d"),
                    _rows(f"steo.{code}.projected", "eia_steo", projected, 5.0, "mb/d"),
                ]
            ),
            source="eia_steo",
        )


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/24_rin.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info] + [e.value for e in at.warning]
    for table in at.dataframe:
        parts.append(table.value.to_string())
    return " ".join(str(part) for part in parts)


def test_an_empty_lake_renders_a_no_data_message_naming_the_pull(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines/eia/pull_steo.py" in said
    assert not _run_page().get("plotly_chart")


def test_the_boundary_between_observed_and_projected_is_stated(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "Observed to Jul 2026" in said
    assert "projected from Aug 2026" in said


def test_the_steo_vintage_is_named(isolated_lake) -> None:
    _seed(isolated_lake)

    assert "2026-10-10" in _said(_run_page())


def test_a_proposed_standard_is_called_proposed(isolated_lake) -> None:
    _seed(isolated_lake, forward_status="proposed")

    said = _said(_run_page())

    assert "proposed" in said.lower()


def test_only_final_standards_never_say_proposed(isolated_lake) -> None:
    _seed(isolated_lake)

    assert "proposed" not in _said(_run_page()).lower()


def test_annual_table_counts_observed_and_projected_months_apart(isolated_lake) -> None:
    _seed(isolated_lake)

    at = _run_page()
    table = at.dataframe[0].value
    total = table[table["Category"] == "Total renewable fuel"].iloc[0]

    assert total["Months observed"] == 3
    assert total["Months projected"] == 2
