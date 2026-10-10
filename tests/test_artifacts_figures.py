"""The Python chart twin: each exhibit kind draws the series the design system promises."""

from __future__ import annotations

from typing import Any

import pytest
from apps.artifacts import figures
from core.design import LIGHT_BLUE, MA_SHORT, NAVY, ORANGE


def _track(name: str, unit: str, points: int = 20) -> dict[str, Any]:
    days = [f"2026-01-{d:02d}" for d in range(1, points + 1)]
    return {
        "name": name,
        "unit": unit,
        "digits": 1,
        "x": days,
        "y": [float(d) for d in range(points)],
    }


def _seasonal() -> dict[str, Any]:
    days = ["2001-01-01", "2001-01-02", "2001-01-03"]
    return {
        "kind": "seasonal",
        "unit": "million barrels",
        "digits": 1,
        "year": 2026,
        "band_label": "5-year range",
        "x": days,
        "band_min": [1.0, 1.0, 1.0],
        "band_max": [3.0, 3.0, 3.0],
        "median": [2.0, 2.0, 2.0],
        "mean": [2.1, 2.1, 2.1],
        "overlays": [
            {
                "name": "MA20",
                "style": "ma20",
                "digits": 1,
                "unit": "x",
                "x": days[:2],
                "y": [2.7, 2.8],
            }
        ],
        "prior": [2.5, 2.5, 2.5],
        "current": [2.8, 2.9, None],
        "annotations": [
            {"x": days[1], "y": 2.9, "axis": "y", "text": "Latest 2.9", "latest": True},
            {"x": days[0], "y": 2.8, "axis": "y", "text": "Low 2.8 · 1 Jan 2026"},
        ],
    }


def test_seasonal_draws_the_current_year_last_in_navy() -> None:
    fig = figures.figure(_seasonal())
    assert [t.name for t in fig.data[1:]] == [
        "5-year range",
        "Median",
        "5-year average",
        "MA20",
        "2025",
        "2026",
    ]
    assert all(t.connectgaps for t in fig.data)
    assert fig.data[1].fill == "tonexty"
    assert (fig.data[2].line.color, fig.data[2].line.dash) == (ORANGE, "dot")
    assert (fig.data[4].line.color, fig.data[4].line.dash) == (MA_SHORT, "dot")
    assert fig.data[5].line.color == LIGHT_BLUE
    assert fig.data[6].line.color == NAVY
    assert [a.text for a in fig.layout.annotations] == ["Latest 2.9", "Low 2.8 · 1 Jan 2026"]
    assert fig.layout.title.text is None


def test_two_units_get_two_tinted_axes() -> None:
    exhibit = {
        "kind": "dual",
        "annotations": [],
        "series": [_track("Production", "million b/d"), _track("Rigs", "rigs")],
    }
    fig = figures.figure(exhibit)
    assert [(t.yaxis, t.line.color) for t in fig.data] == [("y", NAVY), ("y2", LIGHT_BLUE)]
    assert fig.layout.yaxis.title.text == "Production, million b/d"
    assert (fig.layout.yaxis2.side, fig.layout.yaxis2.overlaying) == ("right", "y")
    assert fig.layout.yaxis2.tickfont.color == LIGHT_BLUE


def test_a_single_series_dual_exhibit_has_no_second_axis() -> None:
    fig = figures.figure({"kind": "dual", "annotations": [], "series": [_track("WTI", "$/bbl")]})
    assert len(fig.data) == 1
    assert "yaxis2" not in fig.layout.to_plotly_json()


def test_short_line_series_show_their_points() -> None:
    exhibit = {"kind": "lines", "annotations": [], "series": [_track("Curve", "$/bbl", points=6)]}
    fig = figures.figure(exhibit)
    assert fig.data[0].mode == "lines+markers"
    assert fig.layout.showlegend is False


def test_bars_keep_the_ranking_top_down_and_grow_with_the_categories() -> None:
    exhibit = {
        "kind": "bars",
        "unit": "% full",
        "digits": 1,
        "categories": [f"C{i}" for i in range(12)],
        "values": [float(i) for i in range(12)],
        "compare": [float(i) + 1 for i in range(12)],
        "value_name": "Latest",
        "compare_name": "Year ago",
    }
    fig = figures.figure(exhibit)
    assert fig.data[1].name == "Latest" and fig.data[1].marker.color == NAVY
    assert list(fig.data[1].y)[-1] == "C0" and list(fig.data[1].x)[-1] == 0.0
    assert fig.layout.height == 30 * 12 + 90


@pytest.mark.parametrize("kind", ["dual", "lines"])
def test_lake_text_is_escaped_before_plotly_draws_it(kind: str) -> None:
    track = _track('<a href="https://example.com">Brent</a>', "<b>$/bbl</b>")
    fig = figures.figure({"kind": kind, "annotations": [], "series": [track]})
    assert "<a" not in fig.data[0].name and "&lt;a" in fig.data[0].name
    assert "<b>" not in fig.data[0].hovertemplate


def test_overlays_sit_behind_the_lead_series_on_its_axis() -> None:
    exhibit = {
        "kind": "dual",
        "annotations": [],
        "series": [_track("Brent", "USD/bbl"), _track("Spread", "USD/bbl")],
        "overlays": [
            {**_track("MA200", "USD/bbl"), "style": "ma200"},
            {**_track("5-year average", "USD/bbl", points=2), "style": "avg5"},
        ],
    }
    fig = figures.figure(exhibit)
    assert [t.name for t in fig.data] == ["MA200", "5-year average", "Brent", "Spread"]
    assert fig.data[0].yaxis is None and fig.data[0].line.width == 1.2
    assert fig.data[1].line.color == ORANGE
