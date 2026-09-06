"""US Oil Market Overview — national balance charts supplementary to page 01 (PADD detail).
Only charts not already shown on page 01 live here (no duplicate Crude/Gasoline/Distillate/
Cushing stock charts)."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from components.lake import read_ts_long
from core.macro import deflate
from core.seasonal import seasonal_stats
from core.theme import (
    LIGHT_BLUE,
    multi_year_overlay_chart,
    seasonal_range_chart,
    simple_time_series_chart,
)

PRODUCTION_RANGE_DAYS = {"6M": 182, "1Y": 365, "2Y": 730, "5Y": 1825, "All": None}
WTI_REAL_BASE_PERIOD = "2018-01-01"

PRODUCTION_INFO = [
    (
        "WCRFPUS2",
        "US Crude Oil Production Estimate",
        "Mbbl/d",
        (
            "Production is up 3.3% on the year at 13,830 Mbbl/d — the shale machine keeps "
            "answering every price signal with more barrels, which is exactly the ceiling "
            "that caps how far this complex can run."
        ),
    ),
    (
        "WCREXUS2",
        "Total US Oil Exports",
        "Mbbl/d",
        (
            "Crude exports are down 7% on the year — someone's keeping more of the marginal "
            "barrel at home, and with domestic stocks still light, that's the more plausible "
            "read than weaker demand abroad."
        ),
    ),
    (
        "WCSSTUS1",
        "US Strategic Petroleum Reserves",
        "Mbbl",
        (
            "The SPR is down 27.3% on the year — that's not a rounding adjustment, it's a "
            "strategic buffer spent down to a level where the next real supply shock has "
            "nowhere near the cushion it used to."
        ),
    ),
    (
        "WTTEXUS2",
        "Total US Oil and Fuel Export",
        "Mbbl/d",
        (
            "Total oil and fuel exports are up 9.5% even as crude exports alone are falling "
            "— the US is exporting more of its barrel as refined product now, not as crude, "
            "and that's a refining-margin story as much as a trade one."
        ),
    ),
]


def _seasonal_section(series_id: str, title: str, unit: str, take: str | None = None) -> None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        st.info(f"No data yet for {series_id} — run `pipelines/eia/pull_wpsr.py`.")
        return

    stats = seasonal_stats(df, value_col="value")
    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    fig = seasonal_range_chart(stats, current_year_series, title=title, unit=unit)
    with card(title):
        st.plotly_chart(fig)
        if take is not None:
            kardamow_take(take)


def _simple_section(
    series_id: str,
    title: str,
    unit: str,
    take: str | None = None,
    window_days: int | None = None,
) -> None:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    if df.empty:
        st.info(f"No data yet for {series_id} — run `pipelines/eia/pull_wpsr.py`.")
        return

    series = df.set_index("ts")["value"]
    if window_days is not None:
        cutoff = series.index.max() - pd.Timedelta(days=window_days)
        series = series[series.index >= cutoff]
    fig = simple_time_series_chart(series, title=title, unit=unit)
    with card(title):
        st.plotly_chart(fig)
        if take is not None:
            kardamow_take(take)


def _latest_value(series_id: str) -> float | None:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return float(df["value"].iloc[-1]) if not df.empty else None


def _production_filter_panel() -> list[tuple[str, str, str, str]]:
    """Collapsible filter panel (accordion + checkboxes + live counts) -- see
    02_gas_storage.py's _country_filter_panel for the same convention."""
    for series_id, _label, _unit, _take in PRODUCTION_INFO:
        st.session_state.setdefault(f"oil_overview_filter_{series_id}", True)
    selected_count = sum(
        st.session_state[f"oil_overview_filter_{sid}"] for sid, _, _, _ in PRODUCTION_INFO
    )

    with st.expander(f"Filter metrics ({selected_count} of {len(PRODUCTION_INFO)} shown)"):
        filter_cols = st.columns(2)
        for i, (series_id, label, unit, _take) in enumerate(PRODUCTION_INFO):
            latest = _latest_value(series_id)
            checkbox_label = f"{label} — {latest:,.0f} {unit}" if latest is not None else label
            with filter_cols[i % 2]:
                st.checkbox(checkbox_label, key=f"oil_overview_filter_{series_id}")

    return [item for item in PRODUCTION_INFO if st.session_state[f"oil_overview_filter_{item[0]}"]]


def _four_week_avg_overlay(
    series_ids: list[str], title: str, unit: str, take: str | None = None
) -> None:
    df = read_ts_long(series_ids=series_ids)
    if df.empty:
        st.info(f"No data yet for {series_ids} — run `pipelines/eia/pull_wpsr.py`.")
        return

    wide = df.pivot_table(index="ts", columns="series_id", values="value")
    combined = wide.sum(axis=1).rolling(4).mean().dropna()
    combined_df = combined.reset_index()
    combined_df.columns = ["ts", "value"]

    # seasonal_stats' default years window excludes the current (ongoing) year by
    # design for band/median purposes — this chart style wants it included, since
    # comparing the current year's partial line against recent years is the point.
    current_year = int(combined_df["ts"].dt.year.max())
    stats = seasonal_stats(combined_df, value_col="value", years=range(2018, current_year + 1))
    fig = multi_year_overlay_chart(stats, title=title, unit=unit)
    with card(title):
        st.plotly_chart(fig)
        if take is not None:
            kardamow_take(take)


def _wti_real_price_section() -> None:
    """The refining-demand caption above already references the crack spread this
    price backdrop drives — this section is that backdrop itself, in real (CPI-
    adjusted) terms via core.macro.deflate (Spec 10), not the nominal quote. The
    dual-line "real vs. nominal, indexed" comparison lives on page 10 (Macro & FX);
    this page's own version is deliberately simpler (one line, real dollars, not an
    index) since here it's context for the production/refining story, not the point
    of the chart."""
    wti = read_ts_long(series_ids=["fred.dcoilwtico"]).sort_values("ts")
    cpi = read_ts_long(series_ids=["fred.cpiaucsl"]).sort_values("ts")
    if wti.empty or cpi.empty:
        st.info("No data yet — run `pipelines/macro/pull_macro.py`.")
        return

    wti_series = wti.set_index("ts")["value"]
    cpi_series = cpi.set_index("ts")["value"]
    real_wti = deflate(wti_series, cpi_series, base_period=WTI_REAL_BASE_PERIOD).tail(730)

    title = "WTI Crude, Real Terms (2018 USD)"
    fig = go.Figure(
        go.Scatter(x=real_wti.index, y=real_wti.values, line={"color": LIGHT_BLUE, "width": 2})
    )
    fig.update_layout(title=title, yaxis_title="$/bbl (2018 USD)")
    with card(title):
        st.plotly_chart(fig)
        kardamow_take(
            "This is the price refiners are actually responding to once inflation's "
            "stripped out — the nominal quote alone overstates how attractive the "
            "crack spread really is versus five years ago."
        )


st.title("US Oil Market Overview")

st.subheader("Refining & stocks")
_seasonal_section(
    "WCRRIUS2",
    "Total US Refinery Demand — Seasonal Range",
    " Mbbl/d",
    take=(
        "Refinery demand is running 649 Mbbl/d above its own median at 17,395 — refiners "
        "are chasing a crack spread that's paying them to process more than the seasonal "
        "pattern says they should."
    ),
)
_seasonal_section(
    "WTESTUS1",
    "US Total Commercial Oil and Product Stock — Seasonal Range",
    " Mbbl",
    take=(
        "The whole commercial complex, crude and products together, sits 20,471 Mbbl "
        "under median — the number that tells you the individual product draws elsewhere "
        "on this dashboard aren't noise, they're additive."
    ),
)
_wti_real_price_section()

st.subheader("Production, exports & reserves")
selected_metrics = _production_filter_panel()
if not selected_metrics:
    st.info("No metrics selected — check at least one above.")
else:
    production_range = st.segmented_control(
        "Time range",
        options=list(PRODUCTION_RANGE_DAYS),
        default="2Y",
        required=True,
        key="oil_overview_range",
    )
    for series_id, title, unit, take in selected_metrics:
        _simple_section(
            series_id, title, unit, take=take, window_days=PRODUCTION_RANGE_DAYS[production_range]
        )

st.subheader("Demand (4-week average, by year)")
_four_week_avg_overlay(
    ["WGFUPUS2"],
    "Finished MOGAS Supplied (4-week avg.)",
    "Mbbl/d",
    take=(
        "Gasoline demand's four-week average is basically flat on the year — flat is the "
        "disappointment here, because peak driving season is supposed to be where this "
        "number stretches, not merely holds."
    ),
)
_four_week_avg_overlay(
    ["WGFUPUS2", "WDIUPUS2", "WKJUPUS2"],
    "US Implied Demand for Gasoline, Distillate & Jet Fuel (4-week avg.)",
    "Mbbl/d",
    take=(
        "Combined gasoline, distillate and jet demand is down 1.5% on the year — the "
        "product draws in the stock charts above are running ahead of underlying "
        "consumption, a gap that eventually closes against price, not just inventory."
    ),
)
