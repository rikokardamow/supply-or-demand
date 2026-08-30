"""Kardamow house chart style. Charts must use this — no ad-hoc colours or styling."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from core.seasonal import REFERENCE_YEAR

NAVY = "#0f2a4a"
LIGHT_BLUE = "#5b9bd5"
RED = "#c0392b"
ORANGE = "#e67e22"
BAND = "rgba(150,150,150,0.25)"
GRID = "#e6e6e6"
TRANSPARENT = "rgba(0,0,0,0)"

_MONTH_STARTS = pd.date_range(f"{REFERENCE_YEAR}-01-01", periods=12, freq="MS")
_DOY_TICKVALS = [d.dayofyear for d in _MONTH_STARTS]
_DOY_TICKTEXT = [d.strftime("%b") for d in _MONTH_STARTS]


def register_kardamow_template() -> None:
    template = go.layout.Template()
    template.layout.paper_bgcolor = TRANSPARENT
    template.layout.plot_bgcolor = TRANSPARENT
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
    extra_annotation_line: str | None = None,
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
    if extra_annotation_line is not None:
        lines.append(extra_annotation_line)

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
    fig.update_layout(
        title=title,
        yaxis_title=unit,
        xaxis={"tickvals": _DOY_TICKVALS, "ticktext": _DOY_TICKTEXT},
    )
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


GREY_LINE = "rgba(120,120,120,0.8)"


def current_vs_prior_year_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """Navy current-year line vs grey prior-year line, for series with too short a
    history for seasonal_range_chart's 5-year median/band (e.g. ENTSOG corridors, ~2
    years of data). `df` has columns ts, value. Since a short pull is a rolling window
    rather than calendar years, both years are reindexed to days-since-window-start
    rather than day-of-year, so they overlay regardless of calendar alignment."""
    df = df.sort_values("ts")
    max_ts = df["ts"].max()
    current_start = max_ts - pd.Timedelta(days=364)
    prior_start = current_start - pd.Timedelta(days=365)

    current = df[df["ts"] >= current_start].copy()
    current["day_offset"] = (current["ts"] - current_start).dt.days

    prior = df[(df["ts"] >= prior_start) & (df["ts"] < current_start)].copy()
    prior["day_offset"] = (prior["ts"] - prior_start).dt.days

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=prior["day_offset"],
            y=prior["value"],
            line={"color": GREY_LINE, "width": 2},
            name="Prior year",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=current["day_offset"],
            y=current["value"],
            line={"color": NAVY, "width": 2.5},
            name="Current year",
        )
    )
    fig.update_layout(title=title, yaxis_title=unit, xaxis_title="Days since window start")
    return fig


def sankey_chart(
    node_labels: list[str], sources: list[int], targets: list[int], values: list[float], title: str
) -> go.Figure:
    fig = go.Figure(
        go.Sankey(
            node={"label": node_labels, "color": NAVY, "pad": 15, "thickness": 15},
            link={"source": sources, "target": targets, "value": values, "color": BAND},
        )
    )
    fig.update_layout(title=title)
    return fig


GREY_LINE_THIN = "rgba(150,150,150,0.9)"


def seasonal_minmaxmean_chart(
    stats_df: pd.DataFrame,
    current_year_series: pd.Series,
    title: str,
    unit: str,
) -> go.Figure:
    """Same lo/hi/median inputs as seasonal_range_chart, drawn as explicit Min/Median/Max
    lines instead of a shaded band — a Kardamow-coloured take on the AGSI-style storage
    dashboard layout (navy current year, orange median matching this house's existing
    median convention, grey min/max). Deliberately still "median", not "mean" — this
    house's seasonal maths is median-based throughout (core.seasonal), and this chart
    doesn't silently switch statistic just to match a reference screenshot's label."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=stats_df.index,
            y=stats_df["lo"],
            line={"color": GREY_LINE_THIN, "width": 1},
            name="Min",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=stats_df.index,
            y=stats_df["hi"],
            line={"color": GREY_LINE_THIN, "width": 1},
            name="Max",
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
    fig.update_layout(
        title=title,
        yaxis_title=unit,
        xaxis={"tickvals": _DOY_TICKVALS, "ticktext": _DOY_TICKTEXT},
    )
    return fig


def fullness_comparison_bars(
    rows: list[tuple[str, float, float]], unit_abs: str, date_label: str, title: str
) -> go.Figure:
    """Horizontal bar comparison — e.g. Current / M-1 / Y-1 — each row (label, pct,
    absolute_value), labelled "XX.X% (YYY unit)" per bar. `rows` is drawn top-to-bottom in
    the order given (Plotly draws categorical y-axes bottom-to-top, so this reverses it)."""
    ordered = list(reversed(rows))
    labels = [label for label, _, _ in ordered]
    pcts = [pct for _, pct, _ in ordered]
    text = [f"{pct:.1f}% ({abs_value:,.0f} {unit_abs})" for _, pct, abs_value in ordered]

    fig = go.Figure(
        go.Bar(
            x=pcts,
            y=labels,
            orientation="h",
            marker={"color": LIGHT_BLUE},
            text=text,
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"{title} <span style='font-size:0.7em'>{date_label}</span>",
        xaxis={"range": [0, 100], "ticksuffix": "%"},
    )
    return fig


# Generation-mix PSR-type colours — a deliberate, documented exception to the 4-colour
# house palette above, per specs/04_entsoe-eu-power.md's own visualisation spec
# ("renewables greens/blues, thermal greys/navy"). Real ENTSO-E PSR type names,
# confirmed live (pipelines/entsoe). Not "ad-hoc" in the sense the house-style rule
# means to prevent — this is one fixed, named mapping reused by every generation-mix
# chart, not a per-chart improvisation.
PSR_COLOURS: dict[str, str] = {
    "Solar": "#f1c40f",
    "Wind Onshore": "#27ae60",
    "Wind Offshore": "#16a085",
    "Hydro Run-of-river and poundage": "#2980b9",
    "Hydro Water Reservoir": "#2980b9",
    "Hydro Pumped Storage": LIGHT_BLUE,
    "Marine": "#1abc9c",
    "Biomass": "#58d68d",
    "Geothermal": "#af7ac5",
    "Other renewable": "#48c9b0",
    "Nuclear": "#8e44ad",
    "Fossil Gas": "#7f8c8d",
    "Fossil Hard coal": "#34495e",
    "Fossil Brown coal/Lignite": "#2c3e50",
    "Fossil Oil": "#95a5a6",
    "Fossil Oil shale": "#95a5a6",
    "Fossil Coal-derived gas": "#7f8c8d",
    "Fossil Peat": "#7f8c8d",
    "Waste": "#943126",
    "Other": "#bdc3c7",
}
PSR_DEFAULT_COLOUR = "#bdc3c7"


def generation_mix_chart(df_wide: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """Stacked area chart, one trace per PSR-type column in `df_wide` (index=ts).
    Column order controls stacking order — pass renewables-then-thermal for a chart
    that reads bottom-up the way the spec intends."""
    fig = go.Figure()
    for psr_type in df_wide.columns:
        fig.add_trace(
            go.Scatter(
                x=df_wide.index,
                y=df_wide[psr_type],
                name=psr_type,
                mode="lines",
                stackgroup="one",
                line={"width": 0.5, "color": PSR_COLOURS.get(psr_type, PSR_DEFAULT_COLOUR)},
                fillcolor=PSR_COLOURS.get(psr_type, PSR_DEFAULT_COLOUR),
            )
        )
    fig.update_layout(title=title, yaxis_title=unit)
    return fig


def gauge_chart(
    value: float,
    title: str,
    max_value: float = 100.0,
    thresholds: tuple[float, float] = (50.0, 75.0),
) -> go.Figure:
    """A single-value gauge (e.g. Ireland's SNSP %) — green/orange/red bands split at
    `thresholds`, needle at `value`. `value` and `thresholds` share `max_value`'s scale
    (e.g. percentage points, 0-100)."""
    low, high = thresholds
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": title},
            gauge={
                "axis": {"range": [0, max_value]},
                "bar": {"color": NAVY},
                "steps": [
                    {"range": [0, low], "color": "#d5f5e3"},
                    {"range": [low, high], "color": "#fdebd0"},
                    {"range": [high, max_value], "color": "#fadbd8"},
                ],
            },
        )
    )
    return fig
