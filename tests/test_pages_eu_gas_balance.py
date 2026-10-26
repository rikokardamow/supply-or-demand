"""`apps/dashboard/pages/25_eu_gas_balance.py` through AppTest against an isolated lake.
All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from core import eu_gas_balance as egb
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).parent.parent
APP_ENTRYPOINT = REPO_ROOT / "apps" / "dashboard" / "app.py"
RUN = pd.Timestamp("2026-10-26")
_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _rows(series_id: str, months, value: float, unit: str, source: str = "derived"):
    return pd.DataFrame(
        {"series_id": series_id, "source": source, "ts": months, "value": value, "unit": unit,
         "geo": "EU", "freq": "M", "revision_date": RUN}
    )[_COLUMNS]  # fmt: skip


def _seed(storage) -> None:
    months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
    future = pd.date_range("2026-01-01", "2026-06-01", freq="MS")
    frames = [_rows(f"derived.eu_gas.route.{r}.observed", months, 1.0, "bcm") for r in egb.ROUTES]
    for line in ("production", "consumption", "stock_build", "power", "industry",
                 "other_final", "other_uses", "imports", "exports"):  # fmt: skip
        frames.append(_rows(f"derived.eu_gas.balance.{line}.observed", months, 2.0, "bcm"))
    for check in ("intra_eu_asymmetry", "unexplained"):
        frames.append(_rows(f"derived.eu_gas.check.{check}.observed", months, 0.1, "bcm"))
    frames.append(_rows("derived.eu_gas.storage.fill_pct.projected", future, 50.0, "%"))
    storage.write_ts_long(pd.concat(frames), source="derived")
    days = pd.date_range("2025-01-01", "2026-01-31", freq="D")
    gie = pd.concat(
        [
            _rows("agsi.EU.full_pct", days, 60.0, "%", "gie"),
            _rows("agsi.EU.gas_in_storage", days, 700.0, "TWh", "gie"),
        ]
    ).assign(freq="D")
    storage.write_ts_long(gie, source="gie")


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/25_eu_gas_balance.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info] + [e.value for e in at.warning]
    return " ".join(str(p) for p in parts)


def test_an_empty_lake_names_both_commands(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines.eurostat_gas.pull" in said
    assert "pipelines.derived.eu_gas_balance" in said


def test_the_projection_is_called_an_assumption_with_its_author(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "An assumption, not a forecast" in said
    assert "assumptions.csv" in said


def test_every_route_appears_in_the_annual_table(isolated_lake) -> None:
    _seed(isolated_lake)

    table = _run_page().dataframe[0].value

    for label in egb.ROUTES.values():
        assert label in table.index, label
    assert table.loc["Norway pipeline", 2025] == 12.0
