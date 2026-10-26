"""Supply-demand model pages as plain data, rendered by both the Streamlit and the Dash app.

Each ``*_view()`` reads the lake and returns a ``PageView``: a header, an optional empty-lake
notice, and an ordered list of sections whose items are figures, tables, captions, source
notes, notices or headline numbers. No UI library is imported here, which is what lets
`apps/dashboard/pages/25-28` (Streamlit) and `apps/dash_app` (Dash) show the same content from one
source. Renderers: ``views.render_streamlit`` and ``apps/dash_app/render.py``.

The rules each page must not let a reader miss are in the page docstrings under
`apps/dashboard/pages/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import core.theme  # noqa: F401  -- registers the "kardamow" template
import pandas as pd
import plotly.graph_objects as go
from core import eu_gas_balance as egb
from core import gas_projection as gp
from core import lng_balance as lb
from core import uk_gas_balance as uk
from core.design import MA_LONG, MA_MID, MA_SHORT
from core.storage import read_ts_long
from core.theme import GREY, LIGHT_BLUE, NAVY, ORANGE, RED
from pipelines.derived.eu_carbon import ASSUMPTIONS_CSV as CARBON_ASSUMPTIONS
from pipelines.derived.eu_carbon import read_auctions
from pipelines.derived.eu_gas_balance import ASSUMPTIONS_CSV as EU_GAS_ASSUMPTIONS
from pipelines.derived.eu_gas_balance import latest_run
from pipelines.derived.uk_gas_balance import ASSUMPTIONS_CSV as UK_GAS_ASSUMPTIONS

Kpi = tuple[str, str, str | None]

# Page titles, also read statically by tests/test_pages_browser.py for the thin pages.
TITLES: dict[str, str] = {
    "eu_gas_view": "EU Gas Balance",
    "uk_gas_view": "UK Gas Balance",
    "eu_carbon_view": "EU Carbon",
    "lng_view": "LNG",
}


@dataclass
class Item:
    kind: Literal["figure", "table", "caption", "note", "info", "kpis"]
    value: go.Figure | pd.DataFrame | str | list[Kpi]


@dataclass
class Section:
    title: str | None
    items: list[Item] = field(default_factory=list)

    def add(
        self,
        kind: Literal["figure", "table", "caption", "note", "info", "kpis"],
        value: go.Figure | pd.DataFrame | str | list[Kpi],
    ) -> Section:
        self.items.append(Item(kind, value))
        return self


@dataclass
class PageView:
    title: str
    freshness: str
    as_of: str | None = None
    empty_source: str | None = None  # set when the lake has nothing for this page
    empty_cadence: str | None = None
    sections: list[Section] = field(default_factory=list)

    def section(self, title: str | None) -> Section:
        new = Section(title)
        self.sections.append(new)
        return new


def _table(rows: pd.DataFrame, kind: str, label: str = "observed") -> pd.DataFrame:
    part = rows[(rows["kind"] == kind) & (rows["label"] == label)]
    return part.pivot(index="ts", columns="name", values="value").sort_index()


def _authors(path: object) -> tuple[str, str]:
    assumptions = pd.read_csv(path)  # type: ignore[call-overload]
    return (
        ", ".join(sorted(set(assumptions["author"]))),
        ", ".join(sorted(set(assumptions["as_of"].astype(str)))),
    )


def line_figure(table: pd.DataFrame, ytitle: str) -> go.Figure:
    """A plain multi-line chart, the house template's stand-in for ``st.line_chart``."""
    fig = go.Figure()
    for col in table.columns:
        fig.add_trace(go.Scatter(x=table.index, y=table[col], mode="lines", name=str(col)))
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text=ytitle)
    return fig


def _empty(view: PageView, source: str, cadence: str, message: str) -> PageView:
    view.empty_source, view.empty_cadence = source, cadence
    view.section(None).add("info", message)
    return view


# --- EU gas balance --------------------------------------------------------------------

EU_CHART_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Norway": (NAVY, ("norway_pipeline",)),
    "Russia (pipeline and LNG)": (RED, ("russia_pipeline", "lng_russia")),
    "North Africa pipeline": (MA_MID, ("north_africa_pipeline",)),
    "South-east corridor": (MA_SHORT, ("southeast_corridor",)),
    "LNG, other than Russia": (LIGHT_BLUE, ("lng_us", "lng_qatar", "lng_other", "lng_unspecified")),
    "UK, neighbours and other": (GREY, ("uk", "neighbour_exports", "other_pipeline")),
}


def _grouped_bars(
    routes: pd.DataFrame, groups: dict[str, tuple[str, tuple[str, ...]]], ytitle: str
) -> go.Figure:
    fig = go.Figure()
    for name, (colour, members) in groups.items():
        cols = [c for c in members if c in routes.columns]
        fig.add_trace(
            go.Bar(x=routes.index, y=routes[cols].sum(axis=1), name=name, marker_color=colour)
        )
    fig.update_layout(template="kardamow", barmode="relative")
    fig.update_yaxes(title_text=ytitle)
    return fig


def eu_gas_view() -> PageView:
    view = PageView(TITLES["eu_gas_view"], freshness="Eurostat monthly · GIE daily")
    derived = latest_run(read_ts_long(series_prefix="derived.eu_gas.", source="derived"))
    gie = read_ts_long(series_ids=["agsi.EU.gas_in_storage", "agsi.EU.full_pct"], source="gie")
    if derived.empty:
        return _empty(
            view,
            "derived.eu_gas",
            "monthly",
            "No EU gas balance in the lake. Run `python -m pipelines.eurostat_gas.pull`, "
            "then `python -m pipelines.derived.eu_gas_balance`.",
        )

    routes = _table(derived, "route").reindex(columns=list(egb.ROUTES))
    balance = _table(derived, "balance")
    checks = _table(derived, "check")
    projected = _table(derived, "storage", "projected")
    filled = derived[(derived["kind"] == "member_sum") & (derived["label"] == "observed")]
    last_month = balance["consumption"].dropna().index.max()
    view.as_of = f"Eurostat to {last_month:%b %Y}"

    recent = routes.dropna().tail(12)
    recent_bal = balance.loc[recent.index]
    fill = gie[gie["series_id"] == "agsi.EU.full_pct"].sort_values("ts")
    view.section(None).add(
        "kpis",
        [
            ("Production, 12m", f"{recent_bal['production'].sum():.0f} bcm", None),
            ("Net imports, 12m", f"{recent.sum().sum():.0f} bcm", None),
            ("Consumption, 12m", f"{recent_bal['consumption'].sum():.0f} bcm", None),
            (
                "Storage now (GIE)",
                f"{fill['value'].iloc[-1]:.1f} % full" if not fill.empty else "n/a",
                f"{fill['ts'].iloc[-1]:%d %b %Y}" if not fill.empty else None,
            ),
        ],
    ).add(
        "caption",
        f"Twelve months to {recent.index.max():%b %Y}, the latest twelve with "
        "every route published.",
    )

    view.section("Net imports by route, monthly").add(
        "figure",
        _grouped_bars(routes.loc["2021":].dropna(), EU_CHART_GROUPS, "bcm per month, net imports"),
    ).add(
        "note",
        "Eurostat nrg_ti_gasm and nrg_te_gasm, EU-27, net of intra-EU trade and of "
        "re-exports. Months whose partner detail does not add up to the published total "
        "are omitted. Route mapping: pipelines/derived/eu_gas/routes.csv.",
    )

    annual = gp.calendar_year(
        pd.concat([routes, balance[["production", "consumption", "stock_build"]]], axis=1)
    ).loc[2019:]
    names = {
        **egb.ROUTES,
        "production": "Production",
        "consumption": "Consumption",
        "stock_build": "Into storage",
    }
    view.section("Annual balance, bcm").add("table", annual.rename(columns=names).T.round(1)).add(
        "note",
        "Calendar-year sums. A blank year has at least one month Eurostat published "
        "incompletely; it is not shown as a partial total. Production months that Eurostat "
        "leaves blank at EU level are rebuilt from member states "
        f"({len(filled)} cells across all lines).",
    )

    uses = balance[["power", "industry", "other_final", "other_uses"]].dropna(how="all")
    uses = uses.loc["2023":].rename(
        columns={
            "power": "Power and heat",
            "industry": "Industry",
            "other_final": "Households, services, other",
            "other_uses": "Own use, losses, non-energy",
        }
    )
    view.section("Consumption by use, monthly").add(
        "figure", line_figure(uses, "bcm per month")
    ).add(
        "note",
        "Eurostat publishes the split for the EU-27 from 2023 only. Own use, losses and "
        "non-energy is consumption minus the other three, computed here.",
    )

    path = view.section("Storage path to end-2027")
    actual = fill.set_index("ts")["value"].loc["2025-01":]
    if "fill_pct" in projected:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=actual.index, y=actual, mode="lines", name="GIE, observed", line={"color": NAVY}
            )
        )
        fig.add_trace(
            go.Scatter(
                x=projected.index,
                y=projected["fill_pct"],
                mode="lines+markers",
                name="Model path (assumption)",
                line={"color": ORANGE, "dash": "dash"},
            )
        )
        fig.update_layout(template="kardamow")
        fig.update_yaxes(title_text="EU storage, % full", rangemode="tozero")
        authors, dates = _authors(EU_GAS_ASSUMPTIONS)
        path.add("figure", fig).add(
            "caption",
            "An assumption, not a forecast. From GIE's level at the end of the last "
            "Eurostat month, each later month adds production plus net imports minus "
            "consumption, each taken as the same month a year earlier times the growth "
            f"set in pipelines/derived/eu_gas/assumptions.csv (by {authors}, {dates}).",
        )
    else:
        path.add(
            "info", "No projection: set growth rates in pipelines/derived/eu_gas/assumptions.csv."
        )
    path.add(
        "note",
        "The path ignores the balance's own residual (see Model checks), so it drifts "
        "by the residual's size each month. Capacity is GIE's latest working gas "
        "volume.",
    )

    model = view.section("Model checks")
    tj = read_ts_long(series_ids=["estat.gas.balance_tj.stk_chg_mg.eu"], source="eurostat_gas")
    tj = tj.sort_values("revision_date").drop_duplicates("ts", keep="last").set_index("ts")
    level = gie[gie["series_id"] == "agsi.EU.gas_in_storage"].set_index("ts")["value"]
    storage = egb.storage_check(tj["value"], level) if not tj.empty else pd.DataFrame()
    if not storage.empty:
        part = storage.loc["2021":]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=part.index, y=part["gie_twh"], name="GIE change", marker_color=GREY))
        fig.add_trace(
            go.Scatter(
                x=part.index,
                y=part["eurostat_twh"],
                mode="lines",
                name="Eurostat stock change",
                line={"color": NAVY},
            )
        )
        fig.update_layout(template="kardamow")
        fig.update_yaxes(title_text="TWh per month")
        corr = storage["eurostat_twh"].corr(storage["gie_twh"])
        model.add("figure", fig).add(
            "caption",
            "Eurostat's reported stock change against GIE's month-end storage change: "
            f"correlation {corr:.3f}, median gap {storage['gap_twh'].abs().median():.1f} "
            f"TWh over {len(storage)} months.",
        )
    recent_checks = checks.loc["2021":].abs()
    model.add(
        "caption",
        "Balance residuals since 2021 (bcm per month, median / largest): intra-EU "
        f"asymmetry {recent_checks['intra_eu_asymmetry'].median():.2f} / "
        f"{recent_checks['intra_eu_asymmetry'].max():.2f}; production plus routes "
        "minus consumption against reported stock change "
        f"{recent_checks['unexplained'].median():.2f} / "
        f"{recent_checks['unexplained'].max():.2f}.",
    )
    model.add(
        "note",
        "Intra-EU asymmetry: Eurostat imports minus exports against the sum of routes, "
        "i.e. member states disagreeing about the same flows. GIE: AGSI+ EU "
        "aggregate.",
    )
    return view


# --- UK gas balance --------------------------------------------------------------------

UK_CHART_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Norway pipeline": (NAVY, ("norway_pipeline",)),
    "Continent (IUK, BBL), net": (MA_MID, ("continent_pipeline",)),
    "Exports to Ireland and Isle of Man": (GREY, ("ireland_exports", "isle_of_man_exports")),
    "LNG: United States": (LIGHT_BLUE, ("lng_us",)),
    "LNG: Qatar": (ORANGE, ("lng_qatar",)),
    "LNG: other": (MA_LONG, ("lng_other",)),
}
UK_DEMAND_LABELS = {
    "demand_power": "Power generation",
    "demand_domestic": "Domestic",
    "demand_industrial": "Industrial",
    "demand_services": "Services",
    "demand_own_use": "Own use (producers, operators, LNG, storage)",
    "demand_other": "Other",
}


def uk_gas_view() -> PageView:
    view = PageView(TITLES["uk_gas_view"], freshness="DESNZ Energy Trends, monthly")
    derived = latest_run(read_ts_long(series_prefix="derived.uk_gas.", source="derived"))
    if derived.empty:
        return _empty(
            view,
            "derived.uk_gas",
            "monthly",
            "No UK gas balance in the lake. Run `python -m pipelines.desnz_gas.pull`, "
            "then `python -m pipelines.derived.uk_gas_balance`.",
        )

    routes = _table(derived, "route").reindex(columns=list(uk.UK_ROUTES))
    balance = _table(derived, "balance")
    lng = _table(derived, "lng_call")["total"]
    lng_projected = _table(derived, "lng_call", "projected")
    checks = _table(derived, "check")
    mirror = _table(derived, "mirror")
    provisional = read_ts_long(series_ids=["desnz.gas.provisional.gb"], source="desnz")
    last_month = balance["production"].dropna().index.max()
    flagged = (
        f" · {last_month:%b %Y} provisional"
        if not provisional.empty and last_month in set(provisional["ts"])
        else ""
    )
    view.as_of = f"DESNZ to {last_month:%b %Y}{flagged}"

    recent = routes.dropna().tail(12)
    recent_bal = balance.reindex(recent.index)
    view.section(None).add(
        "kpis",
        [
            ("Production, 12m", f"{recent_bal['production'].sum():.1f} bcm", None),
            ("Norway pipeline, 12m", f"{recent['norway_pipeline'].sum():.1f} bcm", None),
            ("Net LNG, 12m", f"{recent[list(uk.LNG_ROUTES)].sum().sum():.1f} bcm", None),
            ("Demand, 12m", f"{recent_bal['demand'].sum():.1f} bcm", None),
        ],
    ).add("caption", f"Twelve months to {recent.index.max():%b %Y}.")

    view.section("Net imports by route, monthly").add(
        "figure", _grouped_bars(routes.loc["2021":], UK_CHART_GROUPS, "bcm per month, net imports")
    ).add(
        "note",
        "DESNZ Energy Trends table 4.3 (flat format), imports positive, exports "
        "negative. Route mapping: pipelines/derived/uk_gas/routes.csv.",
    )

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
    view.section("Annual balance, bcm").add("table", annual.rename(columns=names).T.round(1)).add(
        "note",
        "Calendar-year sums; a year missing any month is blank. Demand is published from "
        "January 2023. Storage withdrawal is DESNZ's stock change, positive when gas "
        "leaves storage.",
    )

    sectors = balance[[c for c in UK_DEMAND_LABELS if c in balance]].dropna(how="all")
    view.section("Demand by sector, monthly").add(
        "figure", line_figure(sectors.rename(columns=UK_DEMAND_LABELS), "bcm per month")
    ).add("note", "DESNZ Energy Trends table 4.2. Own use groups four published lines.")

    call = view.section("Call on LNG")
    if not lng_projected.empty:
        fig = go.Figure()
        observed = lng.loc["2023":]
        fig.add_trace(
            go.Bar(x=observed.index, y=observed, name="Net LNG imports", marker_color=NAVY)
        )
        fig.add_trace(
            go.Bar(
                x=lng_projected.index,
                y=lng_projected["total"],
                name="Call on LNG (assumption)",
                marker_color=ORANGE,
                opacity=0.6,
            )
        )
        fig.update_layout(template="kardamow", barmode="overlay")
        fig.update_yaxes(title_text="bcm per month")
        by_year = lng_projected["total"].groupby(pd.DatetimeIndex(lng_projected.index).year).sum()
        authors, dates = _authors(UK_GAS_ASSUMPTIONS)
        call.add("figure", fig).add(
            "caption",
            "An assumption, not a forecast. LNG needed = demand - production - "
            "biomethane - storage withdrawal - net pipeline imports, each the same month "
            "a year earlier times the growth in pipelines/derived/uk_gas/assumptions.csv "
            f"(by {authors}, {dates}). Projected totals: "
            + "; ".join(f"{y} {v:.1f} bcm" for y, v in by_year.items())
            + " (a partial year sums only its projected months).",
        )
    else:
        call.add(
            "info", "No projection: set growth rates in pipelines/derived/uk_gas/assumptions.csv."
        )
    losses = balance["losses_statdiff"].dropna().tail(12)
    call.add(
        "note",
        "On history this identity equals net LNG imports to within rounding. The "
        "projection leaves out losses and the statistical difference: "
        f"{losses.sum():+.1f} bcm over the latest twelve published months.",
    )

    model = view.section("Model checks")
    if not mirror.empty:
        part = mirror.loc["2018":]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=part.index,
                y=part["uk_view"],
                mode="lines",
                name="As the UK records it",
                line={"color": NAVY},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=part.index,
                y=part["eu_view"],
                mode="lines",
                name="As the EU records it",
                line={"color": LIGHT_BLUE, "dash": "dash"},
            )
        )
        fig.update_layout(template="kardamow")
        fig.update_yaxes(title_text="UK net exports to the EU, bcm per month")
        corr = mirror["uk_view"].corr(mirror["eu_view"])
        gap = (mirror["eu_view"] - mirror["uk_view"]).loc["2023":]
        model.add("figure", fig).add(
            "caption",
            f"The same flows seen from both sides: correlation {corr:.3f} over "
            f"{len(mirror)} months. Since 2023 the EU records {gap.median() * 1000:.0f} "
            "mcm a month more than the UK sends (median), a measurement asymmetry "
            "between the two statistics.",
        )
    model.add(
        "caption",
        "Routes against published net imports: largest gap "
        f"{checks['route_gap'].abs().max() * 1000:.1f} mcm. Net-supply identity: "
        f"largest gap {checks['supply_gap'].abs().max() * 1000:.1f} mcm.",
    )
    model.add("note", "EU view: derived.eu_gas route 'United Kingdom' (Eurostat), page 25.")
    return view


# --- EU carbon -------------------------------------------------------------------------

SECTOR_COLOURS = {
    "emissions_combustion": ("Combustion of fuels", NAVY),
    "emissions_industry": ("Industry", MA_MID),
    "emissions_aviation": ("Aviation", LIGHT_BLUE),
    "emissions_maritime": ("Shipping (reported, before phase-in)", ORANGE),
}


def eu_carbon_view() -> PageView:
    view = PageView(TITLES["eu_carbon_view"], freshness="EEX primary auctions · EU Union Registry")
    derived = latest_run(read_ts_long(series_prefix="derived.eu_carbon.", source="derived"))
    if derived.empty:
        view.freshness = "EEX auctions · EU Union Registry"
        return _empty(
            view,
            "derived.eu_carbon",
            "after each pull",
            "No EU carbon balance in the lake. Run `python -m pipelines.carbon.pull`, "
            "then `python -m pipelines.derived.eu_carbon`.",
        )

    ets = _table(derived, "ets")
    observed = _table(derived, "balance")
    projected = _table(derived, "balance", "projected")
    complete = _table(derived, "check")["complete"]
    prices = _table(derived, "price")
    auctions = read_auctions()
    eua = auctions[auctions["product"] == "eua"].dropna(subset=["price"]).sort_values("ts")
    last = eua.iloc[-1]
    latest_year = ets.index.max()
    view.as_of = f"EEX to {last['ts']:%d %b %Y} · registry to {latest_year:%Y}"

    recent = eua.tail(20)
    last_full = observed.index.max()
    view.section(None).add(
        "kpis",
        [
            ("Latest auction price", f"€{last['price']:.2f}/t", f"{last['ts']:%d %b}"),
            ("20-auction average", f"€{recent['price'].mean():.2f}/t", None),
            (f"Emissions {last_full:%Y}", f"{ets.loc[last_full, 'emissions_total']:.0f} Mt", None),
            (f"Surplus {last_full:%Y}", f"{observed.loc[last_full, 'surplus']:+.0f} Mt", None),
        ],
    )

    daily = eua.loc[eua["ts"] >= "2021-01-01"]
    monthly = prices["monthly_mean"].loc["2021":]
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
    vwap = prices["annual_vwap"].dropna()
    view.section("Auction clearing price, general allowances").add("figure", fig).add(
        "caption",
        "Volume-weighted annual average: "
        + "; ".join(f"{ts:%Y} €{v:.2f}" for ts, v in vwap.items())
        + f" ({vwap.index.max():%Y} to date).",
    ).add(
        "note",
        "EEX primary auctions, contract T3PA, one auction a day. An auction clearing "
        "price, not a continuous market price. Cancelled auctions have no price and are "
        "left out.",
    )

    fig = go.Figure()
    for col, (name, colour) in SECTOR_COLOURS.items():
        fig.add_trace(
            go.Bar(x=pd.DatetimeIndex(ets.index).year, y=ets[col], name=name, marker_color=colour)
        )
    fig.update_layout(template="kardamow", barmode="stack")
    fig.update_yaxes(title_text="Verified emissions, Mt CO2e")
    emissions = view.section("Verified emissions by sector").add("figure", fig)
    if not bool(complete.iloc[-1]):
        emissions.add(
            "caption",
            f"{latest_year:%Y} is still being reported: its accounts fall "
            "short of the prior year's, so its total is shown but left out "
            "of the balance.",
        )
    emissions.add(
        "note",
        "EU Union Registry verified emissions, EU ETS scope without Great Britain "
        "for every year, from 2013 (earlier years are not comparable). Combustion "
        "of fuels includes industrial boilers as well as power and heat.",
    )

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
    table = pd.concat([observed.assign(Basis="observed"), projected.assign(Basis="assumption")])
    table = table.rename(
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
    authors, dates = _authors(CARBON_ASSUMPTIONS)
    view.section("Allowance balance").add("figure", fig).add("table", table.round(1)).add(
        "caption",
        "Assumption rows are not a forecast: each line repeats the previous year scaled "
        f"by pipelines/derived/eu_carbon/assumptions.csv (by {authors}, {dates}).",
    ).add(
        "note",
        "Supply: free allocation (registry, Articles 10a(1), 10a(7) and 10c) plus EEX "
        "auction volumes, general and aviation allowances. To surrender: verified "
        "emissions with shipping at its phase-in (pipelines/carbon/maritime_phase_in.csv). "
        "Surplus is an annual flow, not the TNAC; the Market Stability Reserve is outside "
        "it.",
    )

    tnac = _table(derived, "tnac")
    if not tnac.empty:
        years = pd.DatetimeIndex(tnac.index).year
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=years,
                y=tnac["tnac"],
                name="Total number of allowances in circulation",
                marker_color=NAVY,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=years,
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
        checked = tnac.dropna(subset=["msr_intake", "rule_intake"])
        worst = (checked["msr_intake"] - checked["rule_intake"]).abs().max() * 1e6
        latest = tnac["tnac"].dropna().index.max()
        view.section("Allowances in circulation and the Market Stability Reserve").add(
            "figure", fig
        ).add(
            "caption",
            f"The TNAC for {latest:%Y} is {tnac.loc[latest, 'tnac']:,.1f} Mt, so "
            f"{tnac.loc[latest, 'msr_intake']:,.1f} Mt leave auctions from September "
            f"{latest.year + 1} to August {latest.year + 2}. The MSR rule, "
            "re-implemented here, reproduces every published intake from "
            f"{checked.index.min():%Y} to {checked.index.max():%Y} "
            + (
                "to within one allowance (rounding)."
                if worst < 1
                else f"to within {worst:,.0f} allowances."
            ),
        ).add(
            "note",
            "European Commission TNAC communications and announcements, each figure "
            "quoted with its source in pipelines/carbon/tnac.csv. Rule: Decision (EU) "
            "2015/1814 as amended by Decision (EU) 2023/852 (24% above 1,096 Mt; above "
            "833 Mt only the excess; below 400 Mt a 100 Mt release).",
        )
    return view


# --- LNG -------------------------------------------------------------------------------

REGION_COLOURS = {
    "europe": NAVY,
    "asia": ORANGE,
    "middle_east_africa": MA_MID,
    "latin_america": LIGHT_BLUE,
    "other": GREY,
    "unmapped": RED,
    "unallocated": MA_LONG,
}
ORIGIN_COLOURS = {
    "united_states": LIGHT_BLUE,
    "qatar": ORANGE,
    "russia": RED,
    "algeria": MA_MID,
    "nigeria": MA_SHORT,
    "norway": NAVY,
    "other": GREY,
    "not_specified": MA_LONG,
}
EXPORTER_COLOURS = {
    "united_states": LIGHT_BLUE,
    "qatar": ORANGE,
    "australia": NAVY,
    "malaysia": MA_MID,
    "nigeria": MA_SHORT,
    "algeria": MA_LONG,
    "trinidad_tobago": GREY,
    "rest": RED,
}
IMPORTER_COLOURS = {
    "china": RED,
    "japan": NAVY,
    "south_korea": MA_MID,
    "india": ORANGE,
    "europe": LIGHT_BLUE,
    "other_asia": MA_SHORT,
    "rest": GREY,
}


def stacked(table: pd.DataFrame, colours: dict[str, str], labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for key, colour in colours.items():
        if key in table and table[key].abs().sum() > 0:
            fig.add_trace(
                go.Bar(x=table.index, y=table[key], name=labels[key], marker_color=colour)
            )
    fig.update_layout(template="kardamow", barmode="relative")
    fig.update_yaxes(title_text="bcm per month")
    return fig


def lng_view() -> PageView:
    view = PageView(TITLES["lng_view"], freshness="EIA · Eurostat · DESNZ, monthly")
    derived = latest_run(read_ts_long(series_prefix="derived.lng.", source="derived"))
    if derived.empty:
        view.freshness = "EIA monthly · Eurostat monthly · DESNZ monthly"
        return _empty(
            view,
            "derived.lng",
            "monthly",
            "No LNG model in the lake. Run `python -m pipelines.eia.pull_lng_exports`, "
            "`python -m pipelines.eurostat_gas.pull`, `python -m pipelines.desnz_gas.pull`, "
            "then `python -m pipelines.derived.lng`.",
        )

    us = _table(derived, "us_exports")
    europe = _table(derived, "europe_imports")
    mirror_eu = _table(derived, "mirror_eu")
    mirror_uk = _table(derived, "mirror_uk")
    view.as_of = f"EIA to {us.index.max():%b %Y} · Europe to {europe.index.max():%b %Y}"

    us12, eu12 = us.tail(12), europe.tail(12)
    view.section(None).add(
        "kpis",
        [
            ("US LNG exports, 12m", f"{us12.sum().sum():.1f} bcm", None),
            ("Share to Europe", f"{us12['europe'].sum() / us12.sum().sum() * 100:.0f} %", None),
            ("Europe LNG imports, 12m", f"{eu12.sum().sum():.1f} bcm", None),
            (
                "US share of Europe's LNG",
                f"{eu12['united_states'].sum() / eu12.sum().sum() * 100:.0f} %",
                None,
            ),
        ],
    ).add(
        "caption",
        f"US: twelve months to {us12.index.max():%b %Y}. Europe: twelve months to "
        f"{eu12.index.max():%b %Y}. Europe's share uses European statistics (see the "
        "last section).",
    )

    view.section("US LNG exports by destination region").add(
        "figure", stacked(us.loc["2019":], REGION_COLOURS, lb.REGIONS)
    ).add(
        "note",
        "EIA natural-gas/move/expc, exports by vessel and by truck, per destination; they "
        "add up to EIA's national total in every month since 2017. Region mapping: "
        "pipelines/derived/lng/destinations.csv.",
    )

    annual = gp.calendar_year(europe).loc[2019:].rename(columns=lb.ORIGINS)
    view.section("Europe's LNG imports by origin").add(
        "figure", stacked(europe.loc["2019":], ORIGIN_COLOURS, lb.ORIGINS)
    ).add("table", annual.T.round(1)).add(
        "note",
        "EU-27 (Eurostat nrg_ti_gasm, LNG) plus UK (DESNZ ET 4.3, LNG), imports from outside "
        "Europe only; months both publish. A year missing any month is blank.",
    )

    fig = go.Figure()
    for frame, name, colour in ((mirror_eu, "EU", NAVY), (mirror_uk, "UK", ORANGE)):
        if frame.empty:
            continue
        years = gp.calendar_year(frame).dropna()
        fig.add_trace(
            go.Bar(
                x=years.index,
                y=years["us_reported"],
                name=f"US reports to {name}",
                marker_color=colour,
            )
        )
        fig.add_trace(
            go.Bar(
                x=years.index,
                y=years["europe_reported"],
                name=f"{name} reports from US",
                marker_color=colour,
                opacity=0.45,
            )
        )
    fig.update_layout(template="kardamow", barmode="group")
    fig.update_yaxes(title_text="bcm per year")
    mirror = view.section("The same cargoes in two statistics").add("figure", fig)
    eu_years = gp.calendar_year(mirror_eu).dropna()
    if not eu_years.empty:
        ratio = (eu_years["europe_reported"] / eu_years["us_reported"]).loc[2021:]
        mirror.add(
            "caption",
            "EU statistics record "
            + ", ".join(f"{y} {r * 100:.0f}%" for y, r in ratio.items())
            + " of the LNG the US reports shipping to the EU. Part of the gap is "
            "cargo the EU books as 'origin not specified'. Part is likely cargo "
            "recorded against a transit or trading country. A cargo in transit at "
            "a month end shifts a month, not a year.",
        )
    mirror.add(
        "note", "US side: EIA exports to EU members and to the UK. Europe side: Eurostat, DESNZ."
    )

    world_exports = _table(derived, "global_exports")
    world_imports = _table(derived, "global_imports")
    if world_exports.empty or world_imports.empty:
        view.section(None).add(
            "info",
            "No global LNG view: run `python -m pipelines.jodi_gas.pull` (needs "
            "JODI_USERNAME and JODI_PASSWORD in .env), then `python -m pipelines.derived.lng`.",
        )
        return view
    imp12 = world_imports.tail(12)
    years = (
        pd.concat(
            {
                "Exports reported": gp.calendar_year(world_exports).sum(axis=1, min_count=1),
                "Imports reported": gp.calendar_year(world_imports).sum(axis=1, min_count=1),
            },
            axis=1,
        )
        .sort_index()
        .loc[2019:]
    )
    view.section("Global LNG: exporters and importers").add(
        "kpis",
        [
            (f"{lb.GROUP_LABELS[k]}, 12m", f"{imp12[k].sum():.1f} bcm", None)
            for k in ("china", "japan", "south_korea", "india")
        ],
    ).add("caption", f"LNG imports, twelve months to {imp12.index.max():%b %Y}.").add(
        "figure", stacked(world_exports.loc["2019":], EXPORTER_COLOURS, lb.GROUP_LABELS)
    ).add("figure", stacked(world_imports.loc["2019":], IMPORTER_COLOURS, lb.GROUP_LABELS)).add(
        "table", years.round(1)
    ).add(
        "caption",
        f"Exports complete to {world_exports.index.max():%b %Y}, imports to "
        f"{world_imports.index.max():%b %Y}: later months are still being reported and "
        "are left out rather than shown as a fall. Reported exports and imports do not "
        "match: Russia's exports are missing, several importers do not report, and "
        "cargoes at sea cross month ends.",
    ).add(
        "note",
        "JODI-Gas World Database via the JODI REST API, NATGAS flows EXPLNG and IMPLNG, "
        "million m3. Europe here also includes Türkiye. Groups: core/lng_balance.py.",
    )
    return view


VIEWS = {
    "eu_gas_balance": eu_gas_view,
    "uk_gas_balance": uk_gas_view,
    "eu_carbon": eu_carbon_view,
    "lng": lng_view,
}
