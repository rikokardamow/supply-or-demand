"""UK gas balance by route and the call on LNG: this repo's own model on DESNZ data.

What this page must not let a reader miss:

- **The UK balances on LNG.** With little storage, the useful forward number is not a fill
  level. It is how much LNG the UK must import once production, Norway and the continent are
  counted.
- **Routes are net.** IUK and BBL flow both ways, and the UK exports to Ireland and the
  continent. A negative route is gas leaving the UK.
- **Sector demand starts in January 2023.** DESNZ marks earlier months not available.
- **The projection is an assumption, not a forecast**: the same month a year earlier, scaled
  by `pipelines/derived/uk_gas/assumptions.csv`, which carries an author and a date.

Method: `core/uk_gas_balance.py`. Mapping: `pipelines/derived/uk_gas/routes.csv`.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, kpi_row, page_header, section, source_note
from core import gas_projection as gp
from core import uk_gas_balance as uk
from core.design import MA_LONG, MA_MID
from core.storage import read_ts_long
from core.theme import GREY, LIGHT_BLUE, NAVY, ORANGE
from pipelines.derived.eu_gas_balance import latest_run
from pipelines.derived.uk_gas_balance import ASSUMPTIONS_CSV

CHART_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Norway pipeline": (NAVY, ("norway_pipeline",)),
    "Continent (IUK, BBL), net": (MA_MID, ("continent_pipeline",)),
    "Exports to Ireland and Isle of Man": (GREY, ("ireland_exports", "isle_of_man_exports")),
    "LNG: United States": (LIGHT_BLUE, ("lng_us",)),
    "LNG: Qatar": (ORANGE, ("lng_qatar",)),
    "LNG: other": (MA_LONG, ("lng_other",)),
}
DEMAND_LABELS = {
    "demand_power": "Power generation",
    "demand_domestic": "Domestic",
    "demand_industrial": "Industrial",
    "demand_services": "Services",
    "demand_own_use": "Own use (producers, operators, LNG, storage)",
    "demand_other": "Other",
}


def _table(rows: pd.DataFrame, kind: str, label: str) -> pd.DataFrame:
    part = rows[(rows["kind"] == kind) & (rows["label"] == label)]
    return part.pivot(index="ts", columns="name", values="value").sort_index()


def _route_chart(routes: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for name, (colour, members) in CHART_GROUPS.items():
        fig.add_trace(
            go.Bar(x=routes.index, y=routes[list(members)].sum(axis=1), name=name,
                   marker_color=colour)
        )  # fmt: skip
    fig.update_layout(template="kardamow", barmode="relative")
    fig.update_yaxes(title_text="bcm per month, net imports")
    return fig


def _lng_chart(observed: pd.Series, projected: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=observed.index, y=observed, name="Net LNG imports", marker_color=NAVY))
    fig.add_trace(
        go.Bar(x=projected.index, y=projected, name="Call on LNG (assumption)",
               marker_color=ORANGE, opacity=0.6)
    )  # fmt: skip
    fig.update_layout(template="kardamow", barmode="overlay")
    fig.update_yaxes(title_text="bcm per month")
    return fig


def _mirror_chart(mirror: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=mirror.index, y=mirror["uk_view"], mode="lines", name="As the UK records it",
                   line={"color": NAVY})
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(x=mirror.index, y=mirror["eu_view"], mode="lines", name="As the EU records it",
                   line={"color": LIGHT_BLUE, "dash": "dash"})
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text="UK net exports to the EU, bcm per month")
    return fig


derived = latest_run(read_ts_long(series_prefix="derived.uk_gas.", source="derived"))
if derived.empty:
    page_header("UK Gas Balance", freshness="DESNZ Energy Trends, monthly")
    empty_state("derived.uk_gas", "monthly", None)
    st.info(
        "No UK gas balance in the lake. Run `python -m pipelines.desnz_gas.pull`, then "
        "`python -m pipelines.derived.uk_gas_balance`."
    )
    st.stop()

routes = _table(derived, "route", "observed").reindex(columns=list(uk.UK_ROUTES))
balance = _table(derived, "balance", "observed")
lng = _table(derived, "lng_call", "observed")["total"]
lng_projected = _table(derived, "lng_call", "projected")
checks = _table(derived, "check", "observed")
mirror = _table(derived, "mirror", "observed")
provisional = read_ts_long(series_ids=["desnz.gas.provisional.gb"], source="desnz")
last_month = balance["production"].dropna().index.max()
flagged = (
    f" · {last_month:%b %Y} provisional"
    if not provisional.empty and last_month in set(provisional["ts"])
    else ""
)

page_header(
    "UK Gas Balance",
    as_of=f"DESNZ to {last_month:%b %Y}{flagged}",
    freshness="DESNZ Energy Trends, monthly",
)

recent = routes.dropna().tail(12)
recent_bal = balance.reindex(recent.index)
kpi_row(
    [
        ("Production, 12m", f"{recent_bal['production'].sum():.1f} bcm", None),
        ("Norway pipeline, 12m", f"{recent['norway_pipeline'].sum():.1f} bcm", None),
        ("Net LNG, 12m", f"{recent[list(uk.LNG_ROUTES)].sum().sum():.1f} bcm", None),
        ("Demand, 12m", f"{recent_bal['demand'].sum():.1f} bcm", None),
    ]
)
st.caption(f"Twelve months to {recent.index.max():%b %Y}.")

with section("Net imports by route, monthly"):
    st.plotly_chart(_route_chart(routes.loc["2021":]))
    source_note(
        "DESNZ Energy Trends table 4.3 (flat format), imports positive, exports negative. "
        "Route mapping: pipelines/derived/uk_gas/routes.csv."
    )

with section("Annual balance, bcm"):
    annual = gp.calendar_year(
        pd.concat([routes, balance[["production", "biomethane", "stock_change", "demand"]]], axis=1)
    ).loc[2019:]
    names = {
        **uk.UK_ROUTES,
        "production": "Production",
        "biomethane": "Biomethane to grid",
        "stock_change": "Storage withdrawal (net)",
        "demand": "Demand",
    }
    st.dataframe(annual.rename(columns=names).T.round(1), width="stretch")
    source_note(
        "Calendar-year sums; a year missing any month is blank. Demand is published from "
        "January 2023. Storage withdrawal is DESNZ's stock change, positive when gas leaves "
        "storage."
    )

with section("Demand by sector, monthly"):
    sectors = balance[[c for c in DEMAND_LABELS if c in balance]].dropna(how="all")
    st.line_chart(sectors.rename(columns=DEMAND_LABELS))
    source_note("DESNZ Energy Trends table 4.2. Own use groups four published lines.")

assumptions = pd.read_csv(ASSUMPTIONS_CSV)
with section("Call on LNG"):
    if not lng_projected.empty:
        st.plotly_chart(_lng_chart(lng.loc["2023":], lng_projected["total"]))
        by_year = lng_projected["total"].groupby(pd.DatetimeIndex(lng_projected.index).year).sum()
        st.caption(
            "An assumption, not a forecast. LNG needed = demand - production - biomethane - "
            "storage withdrawal - net pipeline imports, each the same month a year earlier "
            "times the growth in pipelines/derived/uk_gas/assumptions.csv (by "
            f"{', '.join(sorted(set(assumptions['author'])))}, "
            f"{', '.join(sorted(set(assumptions['as_of'].astype(str))))}). Projected totals: "
            + "; ".join(f"{y} {v:.1f} bcm" for y, v in by_year.items())
            + " (a partial year sums only its projected months)."
        )
    else:
        st.info("No projection: set growth rates in pipelines/derived/uk_gas/assumptions.csv.")
    losses = balance["losses_statdiff"].dropna().tail(12)
    source_note(
        "On history this identity equals net LNG imports to within rounding. The projection "
        "leaves out losses and the statistical difference: "
        f"{losses.sum():+.1f} bcm over the latest twelve published months."
    )

with section("Model checks"):
    if not mirror.empty:
        st.plotly_chart(_mirror_chart(mirror.loc["2018":]))
        corr = mirror["uk_view"].corr(mirror["eu_view"])
        gap = (mirror["eu_view"] - mirror["uk_view"]).loc["2023":]
        st.caption(
            f"The same flows seen from both sides: correlation {corr:.3f} over {len(mirror)} "
            f"months. Since 2023 the EU records {gap.median() * 1000:.0f} mcm a month more "
            "than the UK sends (median), a measurement asymmetry between the two statistics."
        )
    st.caption(
        "Routes against published net imports: largest gap "
        f"{checks['route_gap'].abs().max() * 1000:.1f} mcm. Net-supply identity: largest gap "
        f"{checks['supply_gap'].abs().max() * 1000:.1f} mcm."
    )
    source_note("EU view: derived.eu_gas route 'United Kingdom' (Eurostat), page 25.")
