"""EU ETS allowance balance and auction prices: this repo's own model on public data.

What this page must not let a reader miss:

- **The price is an auction clearing price** (EEX primary auctions, one a day), not a
  continuous market price. No futures settlement is used.
- **The surplus is an annual flow**: supply (free allocation plus auctions) minus what must
  be surrendered. It is not the Total Number of Allowances in Circulation, and the Market
  Stability Reserve is outside it.
- **The latest registry year may be incomplete.** It is extracted soon after the reporting
  deadline. A year that falls short of the prior year's reporting count is left out of
  the balance.
- **Shipping counts at its legislated phase-in** (40% of 2024 emissions, 70% of 2025, 100%
  from 2026), from a committed and cited file.
- **The projection is an assumption, not a forecast.**
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, kpi_row, page_header, section, source_note
from core.design import MA_MID
from core.storage import read_ts_long
from core.theme import GREY, LIGHT_BLUE, NAVY, ORANGE, RED
from pipelines.derived.eu_carbon import ASSUMPTIONS_CSV, read_auctions
from pipelines.derived.eu_gas_balance import latest_run

SECTOR_COLOURS = {
    "emissions_combustion": ("Combustion of fuels", NAVY),
    "emissions_industry": ("Industry", MA_MID),
    "emissions_aviation": ("Aviation", LIGHT_BLUE),
    "emissions_maritime": ("Shipping (reported, before phase-in)", ORANGE),
}


def _table(rows: pd.DataFrame, kind: str, label: str) -> pd.DataFrame:
    part = rows[(rows["kind"] == kind) & (rows["label"] == label)]
    return part.pivot(index="ts", columns="name", values="value").sort_index()


def _price_chart(daily: pd.DataFrame, monthly: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["ts"],
            y=daily["price"],
            mode="markers",
            name="Auction clearing price",
            marker={"color": GREY, "size": 3},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=monthly.index, y=monthly, mode="lines", name="Monthly mean", line={"color": NAVY}
        )
    )
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text="€ per tonne CO2")
    return fig


def _emissions_chart(ets: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col, (name, colour) in SECTOR_COLOURS.items():
        fig.add_trace(
            go.Bar(x=pd.DatetimeIndex(ets.index).year, y=ets[col], name=name, marker_color=colour)
        )
    fig.update_layout(template="kardamow", barmode="stack")
    fig.update_yaxes(title_text="Verified emissions, Mt CO2e")
    return fig


def _balance_chart(observed: pd.DataFrame, projected: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for frame, label, opacity in ((observed, "", 1.0), (projected, " (assumption)", 0.45)):
        if frame.empty:
            continue
        years = pd.DatetimeIndex(frame.index).year
        fig.add_trace(
            go.Bar(
                x=years,
                y=frame["supply"],
                name=f"Supply{label}",
                marker_color=NAVY,
                opacity=opacity,
            )
        )
        fig.add_trace(
            go.Bar(
                x=years,
                y=frame["demand"],
                name=f"To surrender{label}",
                marker_color=LIGHT_BLUE,
                opacity=opacity,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=years,
                y=frame["surplus"],
                mode="lines+markers",
                name=f"Surplus{label}",
                line={"color": RED, "dash": "solid" if not label else "dash"},
            )
        )
    fig.update_layout(template="kardamow", barmode="group")
    fig.update_yaxes(title_text="Mt (allowances)")
    return fig


derived = latest_run(read_ts_long(series_prefix="derived.eu_carbon.", source="derived"))
if derived.empty:
    page_header("EU Carbon", freshness="EEX auctions · EU Union Registry")
    empty_state("derived.eu_carbon", "after each pull", None)
    st.info(
        "No EU carbon balance in the lake. Run `python -m pipelines.carbon.pull`, then "
        "`python -m pipelines.derived.eu_carbon`."
    )
    st.stop()

ets = _table(derived, "ets", "observed")
observed = _table(derived, "balance", "observed")
projected = _table(derived, "balance", "projected")
complete = _table(derived, "check", "observed")["complete"]
prices = _table(derived, "price", "observed")
auctions = read_auctions()
eua = auctions[auctions["product"] == "eua"].dropna(subset=["price"]).sort_values("ts")
last = eua.iloc[-1]
latest_year = ets.index.max()

page_header(
    "EU Carbon",
    as_of=f"EEX to {last['ts']:%d %b %Y} · registry to {latest_year:%Y}",
    freshness="EEX primary auctions · EU Union Registry",
)

recent = eua.tail(20)
last_full = observed.index.max()
kpi_row(
    [
        ("Latest auction price", f"€{last['price']:.2f}/t", f"{last['ts']:%d %b}"),
        ("20-auction average", f"€{recent['price'].mean():.2f}/t", None),
        (f"Emissions {last_full:%Y}", f"{ets.loc[last_full, 'emissions_total']:.0f} Mt", None),
        (f"Surplus {last_full:%Y}", f"{observed.loc[last_full, 'surplus']:+.0f} Mt", None),
    ]
)

with section("Auction clearing price, general allowances"):
    st.plotly_chart(
        _price_chart(eua.loc[eua["ts"] >= "2021-01-01"], prices["monthly_mean"].loc["2021":])
    )
    vwap = prices["annual_vwap"].dropna()
    st.caption(
        "Volume-weighted annual average: "
        + "; ".join(f"{ts:%Y} €{v:.2f}" for ts, v in vwap.items())
        + f" ({vwap.index.max():%Y} to date)."
    )
    source_note(
        "EEX primary auctions, contract T3PA, one auction a day. An auction clearing price, not "
        "a continuous market price. Cancelled auctions have no price and are left out."
    )

with section("Verified emissions by sector"):
    st.plotly_chart(_emissions_chart(ets))
    if not bool(complete.iloc[-1]):
        st.caption(
            f"{latest_year:%Y} is still being reported: its accounts fall short of the prior "
            "year's, so its total is shown but left out of the balance."
        )
    source_note(
        "EU Union Registry verified emissions, EU ETS scope without Great Britain for every "
        "year, from 2013 (earlier years are not comparable). Combustion of fuels includes "
        "industrial boilers as well as power and heat."
    )

assumptions = pd.read_csv(ASSUMPTIONS_CSV)
with section("Allowance balance"):
    st.plotly_chart(_balance_chart(observed, projected))
    table = pd.concat(
        [observed.assign(Basis="observed"), projected.assign(Basis="assumption")]
    ).rename(
        columns={
            "free_allocation": "Free allocation",
            "auctioned": "Auctioned",
            "supply": "Supply",
            "demand": "To surrender",
            "surplus": "Surplus",
            "cumulative_surplus": "Cumulative surplus",
        }
    )
    table.index = pd.DatetimeIndex(table.index).year
    st.dataframe(table.round(1), width="stretch")
    st.caption(
        "Assumption rows are not a forecast: each line repeats the previous year scaled by "
        "pipelines/derived/eu_carbon/assumptions.csv (by "
        f"{', '.join(sorted(set(assumptions['author'])))}, "
        f"{', '.join(sorted(set(assumptions['as_of'].astype(str))))})."
    )
    source_note(
        "Supply: free allocation (registry, Articles 10a(1), 10a(7) and 10c) plus EEX auction "
        "volumes, general and aviation allowances. To surrender: verified emissions with "
        "shipping at its phase-in (pipelines/carbon/maritime_phase_in.csv). Surplus is an annual "
        "flow, not the TNAC; the Market Stability Reserve is outside it."
    )

tnac = _table(derived, "tnac", "observed")
if not tnac.empty:
    with section("Allowances in circulation and the Market Stability Reserve"):
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=pd.DatetimeIndex(tnac.index).year,
                y=tnac["tnac"],
                name="Total number of allowances in circulation",
                marker_color=NAVY,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=pd.DatetimeIndex(tnac.index).year,
                y=tnac["msr_intake"],
                mode="lines+markers",
                name="MSR intake (next Sep-Aug)",
                line={"color": RED},
            )
        )
        for level, label in ((1096, "1,096 Mt"), (833, "833 Mt"), (400, "400 Mt")):
            fig.add_hline(y=level, line={"color": GREY, "dash": "dot"}, annotation_text=label)
        fig.update_layout(template="kardamow")
        fig.update_yaxes(title_text="Mt (allowances)")
        st.plotly_chart(fig)
        checked = tnac.dropna(subset=["msr_intake", "rule_intake"])
        worst = (checked["msr_intake"] - checked["rule_intake"]).abs().max() * 1e6
        latest = tnac["tnac"].dropna().index.max()
        st.caption(
            f"The TNAC for {latest:%Y} is {tnac.loc[latest, 'tnac']:,.1f} Mt, so "
            f"{tnac.loc[latest, 'msr_intake']:,.1f} Mt leave auctions from September "
            f"{latest.year + 1} to August {latest.year + 2}. The MSR rule, re-implemented here, "
            f"reproduces every published intake from {checked.index.min():%Y} to "
            f"{checked.index.max():%Y} "
            + (
                "to within one allowance (rounding)."
                if worst < 1
                else f"to within {worst:,.0f} allowances."
            )
        )
        source_note(
            "European Commission TNAC communications and announcements, each figure quoted with "
            "its source in pipelines/carbon/tnac.csv. Rule: Decision (EU) 2015/1814 as amended by "
            "Decision (EU) 2023/852 (24% above 1,096 Mt; above 833 Mt only the excess; below "
            "400 Mt a 100 Mt release)."
        )
