"""`apps/dashboard/pages/27_eu_carbon.py` through AppTest. All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP_ENTRYPOINT = Path(__file__).parent.parent / "apps" / "dashboard" / "app.py"
RUN = pd.Timestamp("2026-10-26")
_COLUMNS = ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _rows(series_id: str, ts, value, unit: str, source: str = "derived", freq: str = "A"):
    return pd.DataFrame(
        {
            "series_id": series_id,
            "source": source,
            "ts": ts,
            "value": value,
            "unit": unit,
            "geo": "EU",
            "freq": freq,
            "revision_date": RUN,
        }
    )[_COLUMNS]


def _seed(storage) -> None:
    years = pd.to_datetime(["2023-01-01", "2024-01-01", "2025-01-01"])
    frames = [
        _rows(f"derived.eu_carbon.ets.{c}.observed", years, 100.0, "Mt")
        for c in (
            "emissions_combustion",
            "emissions_industry",
            "emissions_aviation",
            "emissions_maritime",
            "emissions_total",
            "free_allocation",
        )
    ]
    for col in (
        "free_allocation",
        "auctioned",
        "supply",
        "demand",
        "surplus",
        "cumulative_surplus",
    ):
        frames.append(_rows(f"derived.eu_carbon.balance.{col}.observed", years[:2], 10.0, "Mt"))
        frames.append(_rows(f"derived.eu_carbon.balance.{col}.projected", years[2:], 5.0, "Mt"))
    frames.append(
        _rows("derived.eu_carbon.check.complete.observed", years, [1.0, 1.0, 0.0], "flag")
    )
    months = pd.date_range("2024-01-01", "2024-03-01", freq="MS")
    frames.append(
        _rows("derived.eu_carbon.price.monthly_mean.observed", months, 70.0, "EUR/t", freq="M")
    )
    frames.append(_rows("derived.eu_carbon.price.annual_vwap.observed", years[1:2], 70.0, "EUR/t"))
    storage.write_ts_long(pd.concat(frames), source="derived")
    days = pd.to_datetime(["2024-03-01", "2024-03-04"])
    storage.write_ts_long(
        pd.concat(
            [
                _rows("eex.eua.auction.price", days, 70.0, "EUR/t", "eex", "D"),
                _rows("eex.eua.auction.volume", days, 1e6, "t", "eex", "D"),
            ]
        ),
        source="eex",
    )


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/27_eu_carbon.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _said(at: AppTest) -> str:
    parts = [e.value for e in at.caption] + [e.value for e in at.markdown]
    parts += [e.value for e in at.info]
    return " ".join(str(p) for p in parts)


def test_an_empty_lake_names_both_commands(isolated_lake) -> None:
    said = _said(_run_page())

    assert "pipelines.carbon.pull" in said and "pipelines.derived.eu_carbon" in said


def test_price_is_labelled_an_auction_price_and_the_open_year_is_flagged(isolated_lake) -> None:
    _seed(isolated_lake)

    said = _said(_run_page())

    assert "auction clearing price, not" in said
    assert "2025 is still being reported" in said
    assert "not a forecast" in said
