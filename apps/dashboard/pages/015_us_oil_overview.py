"""US Oil Market Overview — national balance charts supplementary to page 01 (PADD detail).
Only charts not already shown on page 01 live here (no duplicate Crude/Gasoline/Distillate/
Cushing stock charts)."""

from __future__ import annotations

import core.theme  # noqa: F401
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import multi_year_overlay_chart, seasonal_range_chart, simple_time_series_chart


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
        st.plotly_chart(fig, use_container_width=True)
        if take is not None:
            kardamow_take(take)


def _simple_section(series_id: str, title: str, unit: str, take: str | None = None) -> None:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    if df.empty:
        st.info(f"No data yet for {series_id} — run `pipelines/eia/pull_wpsr.py`.")
        return

    series = df.set_index("ts")["value"]
    fig = simple_time_series_chart(series, title=title, unit=unit)
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        if take is not None:
            kardamow_take(take)


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
        st.plotly_chart(fig, use_container_width=True)
        if take is not None:
            kardamow_take(take)


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

st.subheader("Production, exports & reserves")
_simple_section(
    "WCRFPUS2",
    "US Crude Oil Production Estimate",
    "Mbbl/d",
    take=(
        "Production is up 3.3% on the year at 13,830 Mbbl/d — the shale machine keeps "
        "answering every price signal with more barrels, which is exactly the ceiling that "
        "caps how far this complex can run."
    ),
)
_simple_section(
    "WCREXUS2",
    "Total US Oil Exports",
    "Mbbl/d",
    take=(
        "Crude exports are down 7% on the year — someone's keeping more of the marginal "
        "barrel at home, and with domestic stocks still light, that's the more plausible "
        "read than weaker demand abroad."
    ),
)
_simple_section(
    "WCSSTUS1",
    "US Strategic Petroleum Reserves",
    "Mbbl",
    take=(
        "The SPR is down 27.3% on the year — that's not a rounding adjustment, it's a "
        "strategic buffer spent down to a level where the next real supply shock has "
        "nowhere near the cushion it used to."
    ),
)
_simple_section(
    "WTTEXUS2",
    "Total US Oil and Fuel Export",
    "Mbbl/d",
    take=(
        "Total oil and fuel exports are up 9.5% even as crude exports alone are falling — "
        "the US is exporting more of its barrel as refined product now, not as crude, and "
        "that's a refining-margin story as much as a trade one."
    ),
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
