"""GDP elasticity of oil demand -- the demand half of the `oil_demand.xlsx` port.

What this page must not let a reader miss, each measured on the real panel 2026-10-10:

- **The US fit is mostly the pandemic.** Its R-squared falls by more than two thirds when
  2020-2021 leaves the panel. Both fits are therefore always shown together.
- **China's slope is not statistically significant** on public data, in either panel. It
  is published with its p-value and called what it is.
- **The euro-area block is nineteen members, without Malta**, and its latest quarter is
  usually absent: smaller members report a month late and a partial sum is no observation.
- **Rest of World is not built.** Russia is absent from JODI and no world GDP series exists.

The specification -- year-on-year percentage change on both sides -- is this repo's, not
the workbook's. Its coefficients are a diagnostic to read beside these, not a target.
"""

from __future__ import annotations

from typing import Any

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, page_header, section, source_note
from core import oil_demand as od
from core.storage import read_ts_long
from core.theme import GREY, NAVY, RED
from pipelines.derived import oil_demand as derived_oil_demand
from pipelines.derived.oil_demand import build_panel, read_gdp_yoy, read_monthly_demand

SIGNIFICANCE = 0.05


def _quarter(ts: pd.Timestamp) -> str:
    return f"{ts.year}-Q{ts.quarter}"


def _fit_row(block: str, panel_name: str, fit: od.ElasticityFit) -> dict[str, object]:
    verdict = (
        "significant at 5 %" if fit.p_value < SIGNIFICANCE else "not statistically significant"
    )
    return {
        "Block": od.BLOCK_LABELS[block],
        "Panel": panel_name,
        "Quarters": fit.n,
        "Window": f"{_quarter(fit.start)} to {_quarter(fit.end)}",
        "Slope": round(fit.slope, 2),
        "Std. error": round(fit.slope_se, 2),
        "p-value": round(fit.p_value, 3),
        "R-squared": round(fit.r_squared, 2),
        "Slope is": verdict,
    }


def _scatter(panel: pd.DataFrame, card: dict[str, Any]) -> go.Figure:
    start, end = od.PANDEMIC_WINDOW
    inside = (panel.index >= start) & (panel.index <= end)
    fit: od.ElasticityFit = card["fit"]
    ex: od.ElasticityFit = card["fit_ex_pandemic"]
    xs = [float(panel["gdp_yoy"].min()), float(panel["gdp_yoy"].max())]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=panel.loc[~inside, "gdp_yoy"], y=panel.loc[~inside, "demand_yoy"],
            mode="markers", name="Quarter", marker={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=panel.loc[inside, "gdp_yoy"], y=panel.loc[inside, "demand_yoy"],
            mode="markers", name="2020-2021", marker={"color": RED},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=xs, y=[fit.intercept + fit.slope * x for x in xs],
            mode="lines", name="Full panel", line={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=xs, y=[ex.intercept + ex.slope * x for x in xs],
            mode="lines", name="Ex-pandemic", line={"color": GREY, "dash": "dash"},
        )
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_xaxes(title_text="Real GDP, % y/y")
    fig.update_yaxes(title_text="Oil demand, % y/y")
    return fig


def _assumption_authors() -> pd.DataFrame:
    """Author and date of each assumed GDP quarter, from the owner's CSV. Empty if the
    file holds no rows -- the page then says the provenance is not recorded rather than
    inventing one."""
    try:
        frame = derived_oil_demand.read_assumptions(derived_oil_demand.ASSUMPTIONS_PATH)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=["block", "quarter", "author", "as_of"])
    return frame[["block", "quarter", "author", "as_of"]]


page_header("Oil Demand", freshness="JODI monthly · OECD quarterly")

try:
    monthly = read_monthly_demand()
    gdp_by_block = {block: read_gdp_yoy(block) for block in od.BLOCKS}
except RuntimeError as exc:
    empty_state("jodi / oecd", "monthly / quarterly", None)
    st.info(
        f"{exc}. Then `python -m pipelines.oecd.pull_gdp` and "
        "`python -m pipelines.derived.oil_demand`."
    )
    st.stop()

panels: dict[str, pd.DataFrame] = {}
cards: dict[str, dict[str, Any]] = {}
refused: dict[str, str] = {}
for block in od.BLOCKS:
    panel = build_panel(block, monthly, gdp_by_block[block])
    panels[block] = panel
    try:
        cards[block] = od.model_card(panel, as_of=pd.Timestamp.now().normalize())
    except ValueError as exc:
        refused[block] = str(exc)

window_start, window_end = od.PANDEMIC_WINDOW

with section("Elasticity by block"):
    rows: list[dict[str, object]] = []
    for block, card in cards.items():
        rows.append(_fit_row(block, "Full panel", card["fit"]))
        rows.append(_fit_row(block, "Ex-pandemic", card["fit_ex_pandemic"]))
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    for block, reason in refused.items():
        st.warning(f"{od.BLOCK_LABELS[block]}: no fit. {reason}.")
    source_note(
        "Slope: percentage-point change in oil demand growth per point of real GDP growth, "
        "both year on year. Ex-pandemic drops "
        f"{_quarter(window_start)} to {_quarter(window_end)} — two years, because a 2021 "
        "change is measured against 2020. Demand: JODI secondary table, total products. "
        "GDP: OECD Quarterly National Accounts, seasonally adjusted, chain-linked volume. "
        "Rest of World is not fitted: Russia does not report to JODI and no world GDP "
        "series exists."
    )

for block, card in cards.items():
    label = od.BLOCK_LABELS[block]
    with section(f"{label} — demand growth against GDP growth"):
        st.plotly_chart(_scatter(panels[block], card))
        st.caption(
            f"Model card. Estimation window {_quarter(card['estimation_start'])} to "
            f"{_quarter(card['estimation_end'])}; "
            f"last refit {pd.Timestamp(card['last_refit']).date()}; "
            f"out-of-sample {card['oos_status']} against the benchmark "
            f"“{card['benchmark']}” (RMSE {card['rmse_model']:.2f} vs "
            f"{card['rmse_benchmark']:.2f}, {card['exceptions']} exceptions in "
            f"{card['n_forecasts']} quarters); structural break test dates "
            f"{card['break_date']}."
        )
        if block == "ea":
            source_note(
                "Euro area ex Malta: nineteen members. Malta has gaps in its reporting and "
                "is 0.29 % of the total. A quarter with any member missing is not shown."
            )

scenario = read_ts_long(series_prefix="derived.oil_demand.", source="derived")
scenario = scenario[scenario["series_id"].str.endswith(".scenario")]
if not scenario.empty:
    with section("Scenario — demand growth implied by assumed GDP growth"):
        table = scenario.assign(
            block=scenario["series_id"].str.split(".").str[2],
            Quarter=scenario["ts"].map(_quarter),
        )
        provenance = _assumption_authors()
        provenance["Quarter"] = provenance["quarter"].map(_quarter)
        table = table.merge(
            provenance[["block", "Quarter", "author", "as_of"]],
            on=["block", "Quarter"],
            how="left",
        )
        table["Block"] = table["block"].map(od.BLOCK_LABELS).fillna(table["block"])
        table["Assumed by"] = table["author"].fillna("not recorded")
        table["Assumption dated"] = table["as_of"].fillna("not recorded")
        st.dataframe(
            table[["Block", "Quarter", "value", "Assumed by", "Assumption dated"]].rename(
                columns={"value": "Demand, % y/y"}
            ),
            hide_index=True,
        )
        st.caption(
            "An assumption, not a forecast. These rows apply the full-panel fit to the GDP "
            "growth set in pipelines/derived/oil_demand/gdp_assumptions.csv; each row names "
            "who assumed that growth and when. Read each beside its block's p-value above."
        )
