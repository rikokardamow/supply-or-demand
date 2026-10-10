"""`apps/dashboard/pages/18_curve.py` must honour the same rank window its own pipeline
does, and must caption the provenance it actually plotted.

`pipelines/derived/curve.py` gates every rank-based series it WRITES to
`valid_rank_window`, because an IBKR capture holds no contract that had already expired
when it was taken -- so before that date `core.curve.nearby_panel`'s `f01` is a deferred
contract wearing a front-month label. The page called `nearby_panel`/`time_spreads`/
`convexity`/`curve_regime` directly with no window at all, so the chart showed exactly the
rows the lake refuses: 316 `cl` `s12` points of which 15 were inside the window and 301
were deferred-vs-deferred spreads labelled `f01 - f02`.

These tests drive the real page through `AppTest`, the same mechanism as
tests/test_pages_smoke.py, against an isolated lake.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).parent.parent
APP_ENTRYPOINT = REPO_ROOT / "apps" / "dashboard" / "app.py"

# cl's own shape: monthly expiries, the earliest 2026-10-20, so the smallest gap is 30
# days and the window opens 2026-09-20 -- well inside the panel's own history below.
_EXPIRIES = {
    "x2026": pd.Timestamp("2026-10-20"),
    "z2026": pd.Timestamp("2026-11-20"),
    "f2027": pd.Timestamp("2026-12-21"),
    "g2027": pd.Timestamp("2027-01-20"),
}
_PRICES = {"x2026": 70.0, "z2026": 71.0, "f2027": 72.0, "g2027": 73.0}
_DATES = pd.bdate_range("2026-01-02", "2026-10-09")
_WINDOW_START = pd.Timestamp("2026-09-20")


def _write_close(storage, contract: str, price: float, dates, metric: str = "close") -> None:
    storage.write_ts_long(
        pd.DataFrame(
            {
                "series_id": f"fut.cl.{contract}.{metric}",
                "source": "ibkr",
                "ts": dates,
                "value": price,
                "unit": "USD/1000 bbl",
                "geo": "CL",
                "freq": "D",
                "revision_date": pd.Timestamp("2026-10-10"),
            }
        ),
        source="ibkr",
    )


def _write_meta(expiries: dict[str, pd.Timestamp]) -> None:
    from pipelines.futures.series_meta import ROLL_RULE, write_series_meta

    write_series_meta(
        pd.DataFrame(
            {
                "root": "cl",
                "contract": list(expiries),
                "expiry": list(expiries.values()),
                "tick_size": 0.01,
                "contract_unit": "1000 bbl",
                "currency": "USD",
                "roll_rule": ROLL_RULE,
                "source": "ibkr",
            }
        )
    )


def _run_page() -> AppTest:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=60)
    at = at.switch_page("pages/18_curve.py").run(timeout=60)
    assert not at.exception, at.exception
    return at


def _chart_timestamps(at: AppTest) -> list[pd.Timestamp]:
    """Every datetime x value plotted anywhere on the page. The curve strip's own x axis
    is rank labels (`f01`...), not dates, so it contributes nothing here."""
    stamps: list[pd.Timestamp] = []
    for chart in at.get("plotly_chart"):
        spec = json.loads(chart.proto.spec)
        for trace in spec["data"]:
            for value in trace.get("x") or []:
                if isinstance(value, str) and value[:2] == "20" and "T" in value:
                    stamps.append(pd.Timestamp(value))
    return stamps


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    """Patching `core.storage.LAKE_ROOT` is enough -- `pipelines/futures/series_meta.py`
    derives its own manifest directory from it, so nothing here can reach the real lake
    or the real contract expiries."""
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def test_rank_derived_charts_plot_only_dates_inside_the_valid_rank_window(
    isolated_lake,
) -> None:
    storage = isolated_lake
    for contract, price in _PRICES.items():
        _write_close(storage, contract, price, _DATES)
    _write_meta(_EXPIRIES)

    at = _run_page()
    stamps = _chart_timestamps(at)

    assert stamps, "no dated series was plotted at all"
    assert min(stamps) >= _WINDOW_START, (
        f"the page plotted {min(stamps).date()}, before the rank window opens on "
        f"{_WINDOW_START.date()} -- those f01 labels are deferred contracts"
    )
    assert max(stamps) == _DATES.max()


def test_the_page_states_the_rank_window_rather_than_truncating_quietly(
    isolated_lake,
) -> None:
    """A restriction has to be visible. A chart silently showing 15 of 316 dates with no
    note is the failure mode this project's own "fails loudly and visibly" rule forbids."""
    storage = isolated_lake
    for contract, price in _PRICES.items():
        _write_close(storage, contract, price, _DATES)
    _write_meta(_EXPIRIES)

    at = _run_page()
    said = " ".join([element.value for element in at.caption] + [i.value for i in at.info])

    assert str(_WINDOW_START.date()) in said
    assert "rank" in said.lower()


def test_the_curve_caption_names_the_metric_actually_plotted(isolated_lake) -> None:
    """The caption claimed `fut.cl.*.settle` while every contract in the panel was
    `.close` -- last-trade data, ten minutes delayed. That is the one labelling
    distinction this whole design rests on."""
    storage = isolated_lake
    for contract, price in _PRICES.items():
        _write_close(storage, contract, price, _DATES)
    _write_meta(_EXPIRIES)

    at = _run_page()
    captions = [element.value for element in at.caption]
    curve_caption = next(c for c in captions if c.startswith("Source: fut.cl"))

    assert "close" in curve_caption
    assert "4" in curve_caption  # all four contracts resolved to .close
    assert ".settle (pipelines/futures), unadjusted ranks." not in curve_caption


def test_a_mixed_panel_caption_reports_both_metrics(isolated_lake) -> None:
    """`lco`'s real panel is 13 of 36 `.close` and the rest `.settle`. A caption naming
    one metric for a mixed panel is wrong whichever metric it names."""
    storage = isolated_lake
    for contract, price in _PRICES.items():
        _write_close(storage, contract, price, _DATES)
    # One contract whose settle rows outnumber its close rows wins settle for that column.
    _write_close(storage, "x2026", 70.5, pd.bdate_range("2025-01-02", "2026-10-09"), "settle")
    _write_meta(_EXPIRIES)

    at = _run_page()
    curve_caption = next(
        c for c in (element.value for element in at.caption) if c.startswith("Source: fut.cl")
    )

    assert "settle" in curve_caption
    assert "close" in curve_caption


def test_the_no_data_message_does_not_claim_settlements_are_the_only_input(
    isolated_lake,
) -> None:
    """With an empty lake the page says what is missing. `.close` is a real, supported
    input to this panel, so "No settlement data yet" misdescribes the gap."""
    _run_page_output = _run_page()
    messages = " ".join(element.value for element in _run_page_output.info)

    assert "close" in messages
