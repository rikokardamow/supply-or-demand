"""EU-27 gas balance by supply route: this repo's own model on Eurostat and GIE data.

What this page must not let a reader miss:

- **Routes are net imports.** Transit gas leaves and re-enters the EU (TAP through Albania,
  TurkStream through Serbia, gas to Switzerland), so gross imports double count. A negative
  route is gas the EU sends out.
- **The partner is where gas last came from, not always where it was produced.** Russian and
  Azeri gas share the south-east corridor and cannot be split.
- **A blank is a blank.** Months Eurostat publishes incompletely (all of 2020, March 2024)
  are left out, never treated as zero, and a year missing any month has no annual total.
- **The projection is an assumption, not a forecast.** It repeats each month of the previous
  year, scaled by the growth rates in `pipelines/derived/eu_gas/assumptions.csv`, which carry
  an author and a date.

Method: `core/eu_gas_balance.py`. Mapping: `pipelines/derived/eu_gas/routes.csv`.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, kpi_row, page_header, section, source_note
from core import eu_gas_balance as egb
from core import gas_projection as gp
from core.design import MA_MID, MA_SHORT
from core.storage import read_ts_long
from core.theme import GREY, LIGHT_BLUE, NAVY, ORANGE, RED
from pipelines.derived.eu_gas_balance import ASSUMPTIONS_CSV, latest_run

# Twelve routes are too many colours for the house palette: the chart groups them.
CHART_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Norway": (NAVY, ("norway_pipeline",)),
    "Russia (pipeline and LNG)": (RED, ("russia_pipeline", "lng_russia")),
    "North Africa pipeline": (MA_MID, ("north_africa_pipeline",)),
    "South-east corridor": (MA_SHORT, ("southeast_corridor",)),
    "LNG, other than Russia": (
        LIGHT_BLUE,
        ("lng_us", "lng_qatar", "lng_other", "lng_unspecified"),
    ),
    "UK, neighbours and other": (GREY, ("uk", "neighbour_exports", "other_pipeline")),
}


def _table(rows: pd.DataFrame, kind: str, label: str) -> pd.DataFrame:
    part = rows[(rows["kind"] == kind) & (rows["label"] == label)]
    return part.pivot(index="ts", columns="name", values="value").sort_index()


def _route_chart(routes: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for name, (colour, members) in CHART_GROUPS.items():
        cols = [c for c in members if c in routes.columns]
        fig.add_trace(
            go.Bar(x=routes.index, y=routes[cols].sum(axis=1), name=name, marker_color=colour)
        )
    fig.update_layout(template="kardamow", barmode="relative")
    fig.update_yaxes(title_text="bcm per month, net imports")
    return fig


def _storage_chart(actual_pct: pd.Series, projected_pct: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=actual_pct.index, y=actual_pct, mode="lines", name="GIE, observed",
            line={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=projected_pct.index, y=projected_pct, mode="lines+markers",
            name="Model path (assumption)", line={"color": ORANGE, "dash": "dash"},
        )
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text="EU storage, % full", rangemode="tozero")
    return fig


def _check_chart(storage: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=storage.index, y=storage["gie_twh"], name="GIE change", marker_color=GREY)
    )
    fig.add_trace(
        go.Scatter(
            x=storage.index, y=storage["eurostat_twh"], mode="lines",
            name="Eurostat stock change", line={"color": NAVY},
        )
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text="TWh per month")
    return fig


derived = latest_run(read_ts_long(series_prefix="derived.eu_gas.", source="derived"))
gie = read_ts_long(series_ids=["agsi.EU.gas_in_storage", "agsi.EU.full_pct"], source="gie")

if derived.empty:
    page_header("EU Gas Balance", freshness="Eurostat monthly · GIE daily")
    empty_state("derived.eu_gas", "monthly", None)
    st.info(
        "No EU gas balance in the lake. Run `python -m pipelines.eurostat_gas.pull`, then "
        "`python -m pipelines.derived.eu_gas_balance`."
    )
    st.stop()

routes = _table(derived, "route", "observed").reindex(columns=list(egb.ROUTES))
balance = _table(derived, "balance", "observed")
checks = _table(derived, "check", "observed")
projected = _table(derived, "storage", "projected")
filled = derived[(derived["kind"] == "member_sum") & (derived["label"] == "observed")]
last_month = balance["consumption"].dropna().index.max()

page_header(
    "EU Gas Balance",
    as_of=f"Eurostat to {last_month:%b %Y}",
    freshness="Eurostat monthly · GIE daily",
)

recent = routes.dropna().tail(12)
recent_bal = balance.loc[recent.index]
fill = gie[gie["series_id"] == "agsi.EU.full_pct"].sort_values("ts")
kpi_row(
    [
        ("Production, 12m", f"{recent_bal['production'].sum():.0f} bcm", None),
        ("Net imports, 12m", f"{recent.sum().sum():.0f} bcm", None),
        ("Consumption, 12m", f"{recent_bal['consumption'].sum():.0f} bcm", None),
        (
            "Storage now (GIE)",
            f"{fill['value'].iloc[-1]:.1f} % full" if not fill.empty else "n/a",
            f"{fill['ts'].iloc[-1]:%d %b %Y}" if not fill.empty else None,
        ),
    ]
)
st.caption(
    f"Twelve months to {recent.index.max():%b %Y}, the latest twelve with every route published."
)

with section("Net imports by route, monthly"):
    st.plotly_chart(_route_chart(routes.loc["2021":].dropna()))
    source_note(
        "Eurostat nrg_ti_gasm and nrg_te_gasm, EU-27, net of intra-EU trade and of re-exports. "
        "Months whose partner detail does not add up to the published total are omitted. "
        "Route mapping: pipelines/derived/eu_gas/routes.csv."
    )

with section("Annual balance, bcm"):
    annual = gp.calendar_year(
        pd.concat([routes, balance[["production", "consumption", "stock_build"]]], axis=1)
    ).loc[2019:]
    names = {
        **egb.ROUTES,
        "production": "Production",
        "consumption": "Consumption",
        "stock_build": "Into storage",
    }
    annual = annual.rename(columns=names)
    st.dataframe(annual.T.round(1), width="stretch")
    source_note(
        "Calendar-year sums. A blank year has at least one month Eurostat published "
        "incompletely; it is not shown as a partial total. Production months that Eurostat "
        "leaves blank at EU level are rebuilt from member states "
        f"({len(filled)} cells across all lines)."
    )

with section("Consumption by use, monthly"):
    uses = balance[["power", "industry", "other_final", "other_uses"]].dropna(how="all")
    uses = uses.loc["2023":].rename(
        columns={
            "power": "Power and heat",
            "industry": "Industry",
            "other_final": "Households, services, other",
            "other_uses": "Own use, losses, non-energy",
        }
    )
    st.line_chart(uses)
    source_note(
        "Eurostat publishes the split for the EU-27 from 2023 only. Own use, losses and "
        "non-energy is consumption minus the other three, computed here."
    )

assumptions = pd.read_csv(ASSUMPTIONS_CSV)
with section("Storage path to end-2027"):
    actual = fill.set_index("ts")["value"].loc["2025-01":]
    if "fill_pct" in projected:
        st.plotly_chart(_storage_chart(actual, projected["fill_pct"]))
        authors = ", ".join(sorted(set(assumptions["author"])))
        dates = ", ".join(sorted(set(assumptions["as_of"].astype(str))))
        st.caption(
            "An assumption, not a forecast. From GIE's level at the end of the last Eurostat "
            "month, each later month adds production plus net imports minus consumption, each "
            "taken as the same month a year earlier times the growth set in "
            f"pipelines/derived/eu_gas/assumptions.csv (by {authors}, {dates})."
        )
    else:
        st.info("No projection: set growth rates in pipelines/derived/eu_gas/assumptions.csv.")
    source_note(
        "The path ignores the balance's own residual (see Model checks), so it drifts by the "
        "residual's size each month. Capacity is GIE's latest working gas volume."
    )

with section("Model checks"):
    tj = read_ts_long(series_ids=["estat.gas.balance_tj.stk_chg_mg.eu"], source="eurostat_gas")
    tj = tj.sort_values("revision_date").drop_duplicates("ts", keep="last").set_index("ts")
    level = gie[gie["series_id"] == "agsi.EU.gas_in_storage"].set_index("ts")["value"]
    storage = egb.storage_check(tj["value"], level)
    if not storage.empty:
        st.plotly_chart(_check_chart(storage.loc["2021":]))
        corr = storage["eurostat_twh"].corr(storage["gie_twh"])
        st.caption(
            f"Eurostat's reported stock change against GIE's month-end storage change: "
            f"correlation {corr:.3f}, median gap {storage['gap_twh'].abs().median():.1f} TWh "
            f"over {len(storage)} months."
        )
    recent_checks = checks.loc["2021":].abs()
    st.caption(
        "Balance residuals since 2021 (bcm per month, median / largest): intra-EU "
        f"asymmetry {recent_checks['intra_eu_asymmetry'].median():.2f} / "
        f"{recent_checks['intra_eu_asymmetry'].max():.2f}; production plus routes minus "
        f"consumption against reported stock change {recent_checks['unexplained'].median():.2f} / "
        f"{recent_checks['unexplained'].max():.2f}."
    )
    source_note(
        "Intra-EU asymmetry: Eurostat imports minus exports against the sum of routes, i.e. "
        "member states disagreeing about the same flows. GIE: AGSI+ EU aggregate."
    )
