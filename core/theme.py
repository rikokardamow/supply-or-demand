"""Kardamow house chart style. Charts must use this — no ad-hoc colours or styling."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

NAVY = "#0f2a4a"
LIGHT_BLUE = "#5b9bd5"
RED = "#c0392b"
ORANGE = "#e67e22"
BAND = "rgba(150,150,150,0.25)"
GRID = "#e6e6e6"


def register_kardamow_template() -> None:
    template = go.layout.Template()
    template.layout.paper_bgcolor = "white"
    template.layout.plot_bgcolor = "white"
    template.layout.colorway = [NAVY, LIGHT_BLUE, RED, ORANGE]
    template.layout.xaxis = {"gridcolor": GRID, "showgrid": True, "zeroline": False}
    template.layout.yaxis = {"gridcolor": GRID, "showgrid": True, "zeroline": False}
    template.layout.legend = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "left",
        "x": 0,
    }
    pio.templates["kardamow"] = template
    pio.templates.default = "kardamow"


register_kardamow_template()


def _year_columns(stats_df: pd.DataFrame) -> list[str]:
    return [c for c in stats_df.columns if c not in ("lo", "hi", "median")]


def seasonal_range_chart(
    stats_df: pd.DataFrame,
    current_year_series: pd.Series,
    title: str,
    unit: str,
) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=stats_df.index,
            y=stats_df["lo"],
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
            name="lo",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=stats_df.index,
            y=stats_df["hi"],
            line={"width": 0},
            fill="tonexty",
            fillcolor=BAND,
            name="Seasonal range",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=stats_df.index,
            y=stats_df["median"],
            line={"color": ORANGE, "width": 2},
            name="Median",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=current_year_series.index,
            y=current_year_series.values,
            line={"color": NAVY, "width": 2.5},
            name="Current year",
        )
    )

    last_doy = current_year_series.index[-1]
    latest = current_year_series.iloc[-1]
    median_at_doy = stats_df["median"].get(last_doy)
    vs_median = latest - median_at_doy if median_at_doy is not None else None

    year_cols = _year_columns(stats_df)
    yoy_pct = None
    if year_cols:
        prior_year_value = stats_df[year_cols[-1]].get(last_doy)
        if prior_year_value:
            yoy_pct = (latest - prior_year_value) / prior_year_value * 100

    lines = [f"Latest: {latest:,.1f}{unit}"]
    if yoy_pct is not None:
        lines.append(f"YoY: {yoy_pct:+.1f}%")
    if vs_median is not None:
        lines.append(f"vs median: {vs_median:+,.1f}{unit}")

    fig.add_annotation(
        x=last_doy,
        y=latest,
        text="<br>".join(lines),
        showarrow=True,
        arrowhead=2,
        ax=40,
        ay=-40,
        align="left",
        bgcolor="white",
        bordercolor=NAVY,
    )
    fig.update_layout(title=title, yaxis_title=unit)
    return fig


def dual_axis_chart(
    left_series: pd.Series,
    right_series: pd.Series,
    title: str,
    left_label: str,
    right_label: str,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=left_series.index,
            y=left_series.values,
            name=left_label,
            line={"color": NAVY},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=right_series.index,
            y=right_series.values,
            name=right_label,
            line={"color": LIGHT_BLUE},
            yaxis="y2",
        )
    )
    fig.update_layout(
        title=title,
        yaxis={"title": left_label, "color": NAVY},
        yaxis2={"title": right_label, "color": LIGHT_BLUE, "overlaying": "y", "side": "right"},
    )
    return fig


def simple_time_series_chart(series: pd.Series, title: str, unit: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(x=series.index, y=series.values, line={"color": NAVY, "width": 2})
    )
    fig.update_layout(title=title, yaxis_title=unit)
    return fig


def multi_year_overlay_chart(stats_df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """One line per year (most recent 4 only), reusing the per-year columns
    core.seasonal.seasonal_stats() already computes — seasonal_range_chart only uses
    them for lo/hi/median, this shows each year's track directly instead."""
    year_cols = [c for c in stats_df.columns if c not in ("lo", "hi", "median")]
    recent_years = sorted(year_cols, key=int)[-4:]
    colours = [RED, ORANGE, LIGHT_BLUE, NAVY]  # oldest -> most recent of the 4

    fig = go.Figure()
    for year, colour in zip(recent_years, colours[-len(recent_years):], strict=False):
        is_current = year == recent_years[-1]
        fig.add_trace(
            go.Scatter(
                x=stats_df.index,
                y=stats_df[year],
                name=year,
                line={"color": colour, "width": 3 if is_current else 2},
            )
        )
    fig.update_layout(title=title, yaxis_title=unit)
    return fig
