"""`apps/dashboard/pages/28_lng.py` through AppTest. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from core import lng_balance as lb
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
         "unit": "bcm", "geo": "EU", "freq": "M", "revision_date": RUN}
    )[_COLUMNS]  # fmt: skip


def _seed(storage) -> None:
    months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
    frames = [_rows(f"derived.lng.us_exports.{r}.observed", months, 1.0) for r in lb.REGIONS]
    frames += [_rows(f"derived.lng.europe_imports.{o}.observed", months, 1.0) for o in lb.ORIGINS]
    for side, value in (("us_reported", 3.0), ("europe_reported", 2.0)):
        frames.append(_rows(f"derived.lng.mirror_eu.{side}.observed", months, value))
        frames.append(_rows(f"derived.lng.mirror_uk.{side}.observed", months, value))
    storage.write_ts_long(pd.concat(frames), source="derived")


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/28_lng.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info]
    return " ".join(str(p) for p in parts)


def test_an_empty_lake_names_every_command(isolated_lake) -> None:
    said = _said(_run_page())

    for command in ("pull_lng_exports", "eurostat_gas.pull", "desnz_gas.pull", "derived.lng"):
        assert command in said


def test_the_mirror_ratio_and_the_missing_asia_are_stated(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "2025 67%" in said  # 24 / 36
    assert "No global LNG view" in said and "pipelines.jodi_gas.pull" in said  # no JODI rows


def test_the_global_view_names_its_gaps(isolated_lake) -> None:
    _seed(isolated_lake)
    months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
    frames = [
        _rows(f"derived.lng.global_exports.{g}.observed", months, 2.0)
        for g in (*lb.EXPORTER_GROUPS, "rest")
    ]
    frames += [
        _rows(f"derived.lng.global_imports.{g}.observed", months, 1.0)
        for g in (*lb.IMPORTER_GROUPS, "rest")
    ]
    isolated_lake.write_ts_long(pd.concat(frames), source="derived")

    said = _said(_run_page())

    assert "Russia's exports are missing" in said
    assert "imports, twelve months to Dec 2025" in said
