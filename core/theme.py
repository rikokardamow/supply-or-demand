"""Kardamow house chart style. Charts must use this — no ad-hoc colours or styling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from core.seasonal import REFERENCE_YEAR

NAVY = "#0f2a4a"
LIGHT_BLUE = "#5b9bd5"
RED = "#c0392b"
ORANGE = "#e67e22"
GREY = "#95a5a6"
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
    template.layout.font = {"family": "Inter, sans-serif", "color": "#1a2733"}
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


def count_bar_chart(series: pd.Series, title: str, unit: str) -> go.Figure:
    """A plain navy bar per period -- e.g. page 09's events-per-week volume chart,
    where the shape of interest is a simple count/volume over time, not a trend line."""
    fig = go.Figure(go.Bar(x=series.index, y=series.values, marker={"color": NAVY}))
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
    # gridstatus (MISO/CAISO) fuel-mix names, confirmed live (Spec 05 Session B) --
    # a distinct naming convention from ENTSO-E's PSR types, mapped onto the same
    # fixed palette rather than introducing a second dict.
    "Natural Gas": "#7f8c8d",
    "Coal": "#34495e",
    "Large Hydro": "#2980b9",
    "Small Hydro": "#2980b9",
    "Hydro": "#2980b9",
    "Battery Storage": LIGHT_BLUE,
    "Batteries": LIGHT_BLUE,
    "Imports": "#bdc3c7",
    "Biogas": "#58d68d",
    "Dual Fuel": "#7f8c8d",
    "Other Fossil Fuels": "#95a5a6",
    "Other Renewables": "#48c9b0",
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


def hour_day_heatmap(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """Hour-of-day (x) x calendar day (y) heatmap -- `df` indexed by an hourly
    DatetimeIndex, single value column. Same navy-to-red diverging colourscale as
    `components/power_maps.py`'s price map, for the same reason (a price/cost
    signal, not a volume) -- reused here rather than introduced ad-hoc."""
    pivot = df.copy()
    index = pd.DatetimeIndex(pivot.index)
    pivot["_day"] = index.date
    pivot["_hour"] = index.hour
    value_col = pivot.columns[0]
    grid = pivot.pivot_table(index="_day", columns="_hour", values=value_col)

    fig = go.Figure(
        go.Heatmap(
            z=grid.to_numpy(),
            x=grid.columns,
            y=[d.isoformat() for d in grid.index],
            colorscale=[[0, NAVY], [0.5, "#f5f5f5"], [1, RED]],
            colorbar={"title": unit},
        )
    )
    fig.update_layout(title=title, xaxis_title="Hour of day", yaxis_title="Date")
    return fig


def category_time_heatmap(
    wide_df: pd.DataFrame, title: str, unit: str, center: float = 100.0
) -> go.Figure:
    """Diverging heatmap: one row per category (e.g. country), one column per time
    period -- `wide_df` indexed by category with time-period columns (e.g. an ESI
    pivot: rows=country, columns=month). Same navy-to-red diverging colourscale as
    hour_day_heatmap, generalised for a category axis instead of hour-of-day, and
    explicitly centred on `center` (e.g. 100 for an index like ESI where 100 is the
    long-run average) via `zmid` rather than relying on the data's own range to
    happen to centre itself."""
    fig = go.Figure(
        go.Heatmap(
            z=wide_df.to_numpy(),
            x=wide_df.columns,
            y=wide_df.index,
            zmid=center,
            colorscale=[[0, NAVY], [0.5, "#f5f5f5"], [1, RED]],
            colorbar={"title": unit},
        )
    )
    fig.update_layout(title=title)
    return fig


def production_vs_quota_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """Grouped bars, navy actual vs grey quota, one group per row -- `df` needs
    columns "country", "actual_kbd", "quota_kbd", "compliance_pct" (exact shape
    of pipelines/opec_momr/transforms.py::production_vs_quota's output). Each
    actual bar is labelled with its compliance % directly, per the spec's own
    "grouped bars + compliance % labels" visualisation note."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["country"],
            y=df["actual_kbd"],
            name="Actual",
            marker_color=NAVY,
            text=[f"{pct:.0f}%" for pct in df["compliance_pct"]],
            textposition="outside",
        )
    )
    fig.add_trace(
        go.Bar(x=df["country"], y=df["quota_kbd"], name="Quota", marker_color=GREY)
    )
    fig.update_layout(title=title, yaxis_title=unit, barmode="group")
    return fig


def revision_waterfall_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """`df` needs columns "label", "value" (exact shape of
    pipelines/opec_momr/transforms.py::revision_waterfall's output) -- red for a
    downward revision, navy for an upward one, per the spec's own "red down,
    navy up" note."""
    fig = go.Figure(
        go.Waterfall(
            x=df["label"],
            y=df["value"],
            measure=["relative"] * len(df),
            increasing={"marker": {"color": NAVY}},
            decreasing={"marker": {"color": RED}},
            connector={"line": {"color": GRID}},
        )
    )
    fig.update_layout(title=title, yaxis_title=unit, showlegend=False)
    return fig


def time_series_area_chart(series: pd.Series, title: str, unit: str) -> go.Figure:
    """Single navy filled-area time series -- "Exhibit-1 style" per the OPEC
    supply spec's oil-on-water note (a plain filled line, not a seasonal band)."""
    fig = go.Figure(
        go.Scatter(
            x=series.index,
            y=series.values,
            line={"color": NAVY, "width": 2},
            fill="tozeroy",
            fillcolor="rgba(15,42,74,0.15)",
        )
    )
    fig.update_layout(title=title, yaxis_title=unit, showlegend=False)
    return fig


# Session C (Spec 19) additions: grouped_agency_bars, dual_axis_inverted_chart,
# sign_agreement_scatter. Kept spec-agnostic (no import of core/fundamentals.py), same
# convention as every primitive above.


def grouped_agency_bars(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """One grouped bar trace per column of `df` (index=period, columns=agency names,
    e.g. iea/eia/opec) -- generalises production_vs_quota_chart's own 2-way grouped-bar
    pattern to N agencies. A column literally named "call_on_opec", if present, is
    drawn as a navy line overlay instead of a bar (same unit, no second axis needed)."""
    fig = go.Figure()
    bar_colours = [NAVY, LIGHT_BLUE, ORANGE, RED]
    bar_cols = [c for c in df.columns if c != "call_on_opec"]
    for col, colour in zip(bar_cols, bar_colours[: len(bar_cols)], strict=False):
        fig.add_trace(go.Bar(x=df.index, y=df[col], name=col, marker_color=colour))

    if "call_on_opec" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["call_on_opec"],
                name="call_on_opec",
                mode="lines+markers",
                line={"color": NAVY, "width": 2},
            )
        )

    fig.update_layout(title=title, yaxis_title=unit, barmode="group")
    return fig


_REGIME_BAND_COLOURS = {
    "tight": "#fadbd8",  # same 3 colours as gauge_chart's own low/mid/high steps --
    "balanced": "#fdebd0",  # not a 4th ad-hoc palette. Low spare capacity ("tight") is
    "ample": "#d5f5e3",  # the dangerous/bullish state, so it takes the red band here.
}


def _add_regime_bands(fig: go.Figure, regime: pd.Series, row: int, col: int) -> None:
    """One shaded vrect per contiguous run of the same regime label (not one per row --
    a dense daily series would otherwise draw thousands of overlapping rects)."""
    if regime.empty:
        return
    change = regime.ne(regime.shift()).cumsum()
    for _, run in regime.groupby(change):
        label = run.iloc[0]
        colour = _REGIME_BAND_COLOURS.get(label)
        if colour is None:
            continue
        fig.add_vrect(
            x0=run.index[0],
            x1=run.index[-1],
            fillcolor=colour,
            opacity=0.5,
            line_width=0,
            row=row,
            col=col,
        )


def dual_axis_inverted_chart(
    spare: pd.Series,
    price: pd.Series,
    vol: pd.Series,
    regime: pd.Series,
    title: str,
    spare_label: str,
    price_label: str,
) -> go.Figure:
    """Row 1: `spare` on the left axis with `autorange="reversed"` ("inverted" per the
    spec's own text -- falling spare capacity visually reads as rising tightness) plus
    `price` on the right axis, with a shaded vrect per contiguous
    core.fundamentals.spare_cap_regime run (tight/balanced/ample). Row 2: `vol` as a
    light-blue filled area (same fill convention as time_series_area_chart)."""
    fig = make_subplots(rows=2, row_heights=[0.7, 0.3], vertical_spacing=0.1, shared_xaxes=True)

    fig.add_trace(
        go.Scatter(x=spare.index, y=spare.values, name=spare_label, line={"color": NAVY}),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=price.index,
            y=price.values,
            name=price_label,
            line={"color": LIGHT_BLUE},
            yaxis="y2",
        ),
        row=1,
        col=1,
    )
    _add_regime_bands(fig, regime, row=1, col=1)

    fig.add_trace(
        go.Scatter(
            x=vol.index,
            y=vol.values,
            name="Realised vol",
            line={"color": LIGHT_BLUE, "width": 1.5},
            fill="tozeroy",
            fillcolor="rgba(91,155,213,0.2)",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=title,
        yaxis={"title": spare_label, "autorange": "reversed"},
        yaxis2={"title": price_label, "overlaying": "y", "side": "right"},
    )
    return fig


def sign_agreement_scatter(
    x: pd.Series, y: pd.Series, title: str, x_label: str, y_label: str
) -> go.Figure:
    """Scatter coloured by sign(x) == sign(y) -- RED ("violates the classical model",
    core.fundamentals.carollo_scatter's own "wrong sign" concept) vs NAVY ("agrees",
    opposite signs) -- a fixed two-colour categorical split, not a continuous scale.
    `x`/`y` are paired on their own index (via an inner join, NaN-dropped) first --
    two independently-resampled series aren't guaranteed identically-labelled, and
    pandas refuses a positional `!=` comparison across mismatched labels."""
    paired = pd.DataFrame({"x": x, "y": y}).dropna()
    agrees = np.sign(paired["x"]) != np.sign(paired["y"])
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=paired.loc[agrees, "x"],
            y=paired.loc[agrees, "y"],
            mode="markers",
            name="Agrees with classical model",
            marker={"color": NAVY},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=paired.loc[~agrees, "x"],
            y=paired.loc[~agrees, "y"],
            mode="markers",
            name="Violates classical model",
            marker={"color": RED},
        )
    )
    fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)
    return fig


# Session D (Spec 18) additions: curve_strip_chart, regime_ribbon_chart,
# scatter_piecewise_fit_chart, bday_heatmap. Kept spec-agnostic (no import of
# core/curve.py) so this module stays reusable house style, not a Spec-18-specific one --
# callers pass plain Series/DataFrames, the same convention every primitive above uses.

_CURVE_STRIP_COLOURS = [NAVY, LIGHT_BLUE, ORANGE, RED]


def curve_strip_chart(
    curves: dict[str, pd.Series], spread_bars: dict[str, float], title: str, unit: str
) -> go.Figure:
    """Row 1: one line per as-of label in `curves` (e.g. "Today"/"-5bd"/"-20bd"/"-252bd"),
    each a Series indexed by rank column (f01, f02, ...). Row 2: a navy bar per named
    spread in `spread_bars` (e.g. s12/s13/s16/s1_12), today's values."""
    fig = make_subplots(rows=2, row_heights=[0.7, 0.3], vertical_spacing=0.15)

    for (label, curve), colour in zip(
        curves.items(), _CURVE_STRIP_COLOURS[: len(curves)], strict=False
    ):
        fig.add_trace(
            go.Scatter(
                x=curve.index, y=curve.values, name=label, line={"color": colour, "width": 2}
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=list(spread_bars.keys()),
            y=list(spread_bars.values()),
            marker={"color": NAVY},
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    fig.update_layout(title=title, yaxis_title=unit)
    return fig


def regime_ribbon_chart(
    price: pd.Series,
    state_codes: pd.Series,
    state_labels: dict[int, str],
    title: str,
    unit: str,
) -> go.Figure:
    """Row 1: navy price line. Row 2: a single-row heatmap, one column per date, coloured
    by `state_codes` (already-encoded small ints, e.g. core.curve.REGIME_CODES) -- a fixed
    categorical scale sized to `state_labels`, so every state gets its own flat colour band
    rather than a continuous gradient implying an ordering between regimes that isn't
    real."""
    n_states = len(state_labels)
    palette = [NAVY, LIGHT_BLUE, RED, ORANGE, GREY, "#8e44ad", "#2c3e50"][:n_states]
    colourscale = []
    for i, colour in enumerate(palette):
        colourscale.append([i / n_states, colour])
        colourscale.append([(i + 1) / n_states, colour])

    fig = make_subplots(rows=2, row_heights=[0.75, 0.25], vertical_spacing=0.08, shared_xaxes=True)
    fig.add_trace(
        go.Scatter(x=price.index, y=price.values, line={"color": NAVY, "width": 2}, name=unit),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Heatmap(
            z=[state_codes.to_numpy()],
            x=state_codes.index,
            y=[""],
            zmin=0,
            zmax=n_states,
            colorscale=colourscale,
            showscale=False,
        ),
        row=2,
        col=1,
    )
    fig.update_layout(title=title, yaxis_title=unit, showlegend=False)
    return fig


def scatter_piecewise_fit_chart(
    x: pd.Series,
    y: pd.Series,
    year: pd.Series,
    bins: list[tuple[float, float]],
    title: str,
    x_label: str,
    y_label: str,
    annotations: list[tuple[float, float, str]] | None = None,
) -> go.Figure:
    """Scatter coloured by `year` (a sequential GREY->NAVY scale, oldest to newest -- the
    one deliberate exception to the 4-colour palette, same documented precedent as
    PSR_COLOURS above, since house style has no built-in year gradient). One straight-line
    fit per (lo, hi) in `bins`, via numpy.polyfit(deg=1) -- no scipy dependency needed for
    a linear fit. `annotations`: labelled markers at explicit (x, y) points (e.g. Apr-2020)."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker={
                "color": year,
                "colorscale": [[0, GREY], [1, NAVY]],
                "colorbar": {"title": "Year"},
                "size": 6,
            },
            name="Observations",
        )
    )

    for lo, hi in bins:
        mask = (x >= lo) & (x < hi)
        if mask.sum() < 2:
            continue
        coeffs = np.polyfit(x[mask], y[mask], deg=1)
        fit_x = np.linspace(lo, hi, 20)
        fit_y = np.polyval(coeffs, fit_x)
        fig.add_trace(
            go.Scatter(
                x=fit_x,
                y=fit_y,
                mode="lines",
                line={"color": RED, "width": 2},
                showlegend=False,
            )
        )

    for ax, ay, label in annotations or []:
        fig.add_annotation(
            x=ax, y=ay, text=label, showarrow=True, arrowhead=2, bgcolor="white", bordercolor=RED
        )

    fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label, showlegend=False)
    return fig


def bday_heatmap(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    """Year (rows) x business-day offset from a roll window's own start (columns) --
    `df` indexed by year (int), one column per offset, values = mean Δs12 that offset,
    that year. Same navy-to-red diverging colourscale as hour_day_heatmap/
    category_time_heatmap, centred on 0 via zmid (a Δ-price series has no natural
    non-zero centre)."""
    fig = go.Figure(
        go.Heatmap(
            z=df.to_numpy(),
            x=df.columns,
            y=df.index,
            zmid=0,
            colorscale=[[0, NAVY], [0.5, "#f5f5f5"], [1, RED]],
            colorbar={"title": unit},
        )
    )
    fig.update_layout(
        title=title, xaxis_title="Business days from roll-window start", yaxis_title="Year"
    )
    return fig


def cointegration_residual_chart(
    ect: pd.Series,
    z: pd.Series,
    title: str,
    unit: str,
    z_entry: float = 1.5,
    z_exit: float = 0.5,
) -> go.Figure:
    """Row 1: the fitted cointegrating relation (beta'y) in navy. Row 2: its rolling
    z-score with the entry bands in red and the exit bands in orange.

    Two rows rather than a dual axis: the ECT is in price units and the z-score is
    dimensionless, so sharing an axis would imply a comparability that isn't there."""
    fig = make_subplots(
        rows=2, row_heights=[0.55, 0.45], vertical_spacing=0.12, shared_xaxes=True
    )
    fig.add_trace(
        go.Scatter(x=ect.index, y=ect.to_numpy(), name="ECT", line={"color": NAVY, "width": 2}),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=z.index, y=z.to_numpy(), name="z-score", line={"color": LIGHT_BLUE, "width": 2}
        ),
        row=2,
        col=1,
    )
    for level, colour, label in (
        (z_entry, RED, "entry"),
        (-z_entry, RED, None),
        (z_exit, ORANGE, "exit"),
        (-z_exit, ORANGE, None),
    ):
        fig.add_hline(
            y=level,
            line={"color": colour, "width": 1, "dash": "dash"},
            annotation_text=label,
            annotation_position="right",
            row=2,
            col=1,
        )
    fig.update_yaxes(title_text=unit, row=1, col=1)
    fig.update_yaxes(title_text="z", row=2, col=1)
    fig.update_layout(title=title)
    return fig


def irf_chart(irf: pd.DataFrame, response_col: str, title: str, unit: str) -> go.Figure:
    """Impulse response over the forecast horizon. `irf` needs a `horizon` column plus
    `response_col`. A zero line is drawn because the sign of the response is the whole
    point of the chart."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=irf["horizon"],
            y=irf[response_col],
            mode="lines+markers",
            name=response_col,
            line={"color": NAVY, "width": 2},
            marker={"size": 5},
        )
    )
    fig.add_hline(y=0.0, line={"color": GREY, "width": 1})
    fig.update_layout(title=title, xaxis_title="Months after shock", yaxis_title=unit)
    return fig


def model_monitor_chart(
    rmse_ratio: pd.Series, trigger: float, title: str, break_date: pd.Timestamp | None = None
) -> go.Figure:
    """Rolling out-of-sample RMSE ratio against the benchmark, with the refit trigger and
    the parity line.

    Parity (1.0) is drawn as well as the trigger because a ratio of 1.02 is already
    *losing* to the benchmark even though it sits inside a 1.05 trigger -- the two lines
    keep that distinction visible, which a single threshold line would hide."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=rmse_ratio.index,
            y=rmse_ratio.to_numpy(),
            name="OOS RMSE ratio",
            line={"color": NAVY, "width": 2},
        )
    )
    fig.add_hline(
        y=1.0,
        line={"color": GREY, "width": 1, "dash": "dot"},
        annotation_text="parity with benchmark",
        annotation_position="top left",
    )
    fig.add_hline(
        y=trigger,
        line={"color": RED, "width": 1, "dash": "dash"},
        annotation_text=f"refit trigger ({trigger})",
        annotation_position="bottom left",
    )
    if break_date is not None:
        # Deliberately add_shape + add_annotation rather than add_vline(annotation_text=).
        # add_vline routes an annotated line through plotly's own
        # shapeannotation.annotation_params_for_line, which averages the line's endpoints
        # with `float(sum(x)) / len(x)` to place the label -- that requires numeric x and
        # raises on a datetime axis (TypeError against both a pandas Timestamp and an ISO
        # string). Caught by tests/test_pages_smoke.py, which is precisely why a page
        # actually has to be rendered rather than merely imported.
        stamp = pd.Timestamp(break_date)
        fig.add_shape(
            type="line",
            x0=stamp,
            x1=stamp,
            yref="paper",
            y0=0,
            y1=1,
            line={"color": ORANGE, "width": 1, "dash": "dash"},
        )
        fig.add_annotation(
            x=stamp,
            yref="paper",
            y=1.02,
            text="structural break",
            showarrow=False,
            font={"color": ORANGE, "size": 11},
        )
    fig.update_layout(title=title, yaxis_title="model RMSE / benchmark RMSE")
    return fig


# --- Spec 21 systematic-engine primitives ------------------------------------------


def signal_board_table(board: pd.DataFrame, title: str) -> go.Figure:
    """One row per strategy: z, position and guardrail state, coloured by position sign.

    A board you cannot read at a glance is not doing its job, so the position cell is
    filled navy for a long and red for a short rather than relying on the reader parsing
    a minus sign.
    """
    if board.empty:
        return go.Figure(layout={"title": title})

    positions = board["position"].fillna(0.0)
    position_fill = [NAVY if v > 0 else RED if v < 0 else GREY for v in positions]
    neutral = ["white"] * len(board)

    fig = go.Figure(
        go.Table(
            header={
                "values": [f"<b>{c}</b>" for c in board.columns],
                "fill_color": NAVY,
                "font": {"color": "white"},
                "align": "left",
            },
            cells={
                "values": [board[c] for c in board.columns],
                "fill": {
                    "color": [
                        neutral if c != "position" else position_fill for c in board.columns
                    ]
                },
                "font": {
                    "color": [
                        ["black"] * len(board) if c != "position" else ["white"] * len(board)
                        for c in board.columns
                    ]
                },
                "align": "left",
                "format": [None, ".2f", ".2f", None][: len(board.columns)],
            },
        )
    )
    fig.update_layout(title=title)
    return fig


def equity_drawdown_chart(
    equity: pd.Series,
    drawdown: pd.Series,
    title: str,
    unit: str,
    benchmark: pd.Series | None = None,
) -> go.Figure:
    """Cumulative log equity above, drawdown below, sharing an x-axis.

    Drawdown gets its own panel rather than a second y-axis: the two are in the same
    units, and stacking them keeps the depth of a drawdown visually proportional to the
    equity it ate.
    """
    fig = make_subplots(
        rows=2, row_heights=[0.68, 0.32], vertical_spacing=0.10, shared_xaxes=True
    )
    fig.add_trace(
        go.Scatter(
            x=equity.index, y=equity.to_numpy(), name="Strategy",
            line={"color": NAVY, "width": 2},
        ),
        row=1,
        col=1,
    )
    if benchmark is not None:
        fig.add_trace(
            go.Scatter(
                x=benchmark.index,
                y=benchmark.to_numpy(),
                name="Benchmark",
                line={"color": GREY, "width": 1.5, "dash": "dash"},
            ),
            row=1,
            col=1,
        )
    fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown.to_numpy(),
            name="Drawdown",
            fill="tozeroy",
            line={"color": RED, "width": 1},
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(title_text=unit, row=1, col=1)
    fig.update_yaxes(title_text="drawdown", row=2, col=1)
    fig.update_layout(title=title)
    return fig


def reaction_curve_chart(current_z: float, title: str) -> go.Figure:
    """Bouchouev's reaction function with today's z marked on it.

    Drawn from the same formula the sizing uses, so the chart cannot drift away from the
    behaviour it claims to describe. The peak at z=1 is the whole point: past it, more
    extreme means smaller.
    """
    z = np.linspace(-3.0, 3.0, 241)
    r = z * np.exp(0.5 * (1.0 - z**2))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=z, y=r, name="R(z)", line={"color": NAVY, "width": 2}))
    fig.add_hline(y=0.0, line={"color": GREY, "width": 1})

    if current_z is not None and np.isfinite(current_z):
        clipped = float(np.clip(current_z, -3.0, 3.0))
        fig.add_trace(
            go.Scatter(
                x=[current_z],
                y=[clipped * np.exp(0.5 * (1.0 - clipped**2))],
                mode="markers+text",
                name="today",
                text=[f"z={current_z:.2f}"],
                textposition="top center",
                marker={"color": RED, "size": 11},
            )
        )
    fig.update_layout(title=title, xaxis_title="z-score", yaxis_title="position")
    return fig


def fractionation_heatmap(
    table: pd.DataFrame, title: str, value: str = "sharpe"
) -> go.Figure:
    """Where the P&L came from: conditions down, bins across.

    `table` is `core.backtest.fractionate`'s own output. Diverging around zero because
    the question is which buckets made money and which lost it, not which were largest.
    """
    if table.empty:
        return go.Figure(layout={"title": title})

    wide = table.pivot_table(index="condition", columns="bin", values=value)
    limit = float(np.nanmax(np.abs(wide.to_numpy()))) or 1.0
    fig = go.Figure(
        go.Heatmap(
            z=wide.to_numpy(),
            x=[str(c) for c in wide.columns],
            y=[str(i) for i in wide.index],
            colorscale=[[0.0, RED], [0.5, "white"], [1.0, NAVY]],
            zmid=0.0,
            zmin=-limit,
            zmax=limit,
            colorbar={"title": value},
        )
    )
    fig.update_layout(title=title, xaxis_title="bin", yaxis_title="condition")
    return fig


def crowding_quadrant_scatter(
    cot_pct: pd.Series, signal_z: pd.Series, title: str
) -> go.Figure:
    """Positioning against signal, with the two inflection corners shaded.

    The corners are the point: a long signal while managed money is already crowded long
    (top right) is a very different trade from the same signal with the crowd short.
    """
    frame = pd.DataFrame({"cot": cot_pct, "z": signal_z}).dropna()
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=frame["cot"],
            y=frame["z"],
            mode="markers",
            name="days",
            marker={"color": NAVY, "size": 4, "opacity": 0.35},
        )
    )
    # Crowded long with a long signal, and crowded short with a short signal.
    for x0, x1, y0, y1 in ((0.95, 1.0, 0.0, 3.0), (0.0, 0.05, -3.0, 0.0)):
        fig.add_shape(
            type="rect",
            x0=x0,
            x1=x1,
            y0=y0,
            y1=y1,
            fillcolor=RED,
            opacity=0.12,
            line={"width": 0},
        )
    fig.add_hline(y=0.0, line={"color": GREY, "width": 1})
    fig.update_layout(
        title=title,
        xaxis_title="managed-money percentile",
        yaxis_title="signal z",
    )
    return fig
