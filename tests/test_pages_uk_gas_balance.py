"""`apps/dashboard/pages/26_uk_gas_balance.py` through AppTest. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from core import uk_gas_balance as uk
from streamlit.testing.v1 import AppTest

APP_ENTRYPOINT = Path(__file__).parent.parent / "apps" / "dashboard" / "app.py"
RUN = pd.Timestamp("2026-10-26")
_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _rows(series_id: str, months, value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"series_id": series_id, "source": "derived", "ts": months, "value": value,
         "unit": "bcm", "geo": "GB", "freq": "M", "revision_date": RUN}
    )[_COLUMNS]  # fmt: skip


def _seed(storage) -> None:
    months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
    future = pd.date_range("2026-01-01", "2026-06-01", freq="MS")
    frames = [_rows(f"derived.uk_gas.route.{r}.observed", months, 1.0) for r in uk.UK_ROUTES]
    for line in ("production", "biomethane", "stock_change", "demand", "demand_power",
                 "losses_statdiff"):  # fmt: skip
        frames.append(_rows(f"derived.uk_gas.balance.{line}.observed", months, 2.0))
    frames.append(_rows("derived.uk_gas.lng_call.total.observed", months, 3.0))
    frames.append(_rows("derived.uk_gas.lng_call.total.projected", future, 1.5))
    for check in ("route_gap", "supply_gap"):
        frames.append(_rows(f"derived.uk_gas.check.{check}.observed", months, 0.0))
    storage.write_ts_long(pd.concat(frames), source="derived")


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/26_uk_gas_balance.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info]
    return " ".join(str(p) for p in parts)


def test_an_empty_lake_names_both_commands(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines.desnz_gas.pull" in said and "pipelines.derived.uk_gas_balance" in said


def test_the_lng_call_is_called_an_assumption(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "An assumption, not a forecast" in said
    assert "2026 9.0 bcm" in said  # six projected months at 1.5


def test_every_route_appears_in_the_annual_table(isolated_lake) -> None:
    _seed(isolated_lake)

    table = _run_page().dataframe[0].value

    for label in uk.UK_ROUTES.values():
        assert label in table.index, label
