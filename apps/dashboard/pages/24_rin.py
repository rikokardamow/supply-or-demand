"""Implied Renewable Fuel Standard mandate -- the mandate half of the RIN workbook port.

What this page must not let a reader miss:

- **A projected month is never shown as an observed one.** The mandate rests on STEO demand,
  and STEO's own history ends at a boundary read live from EIA's actuals. Past it, every
  exhibit marks the value projected: a dashed segment, a caption naming the boundary month,
  and a column count of observed against projected months.
- **A proposed EPA standard is named proposed.** Every committed standard is final today, but
  the reference file carries a status per row, and the page reads it rather than assuming it.
- **This is the mandate, not the balance.** Actual RIN generation (EPA EMTS) is not ported.

Checked against the workbook 2026-10-26: see `pipelines/derived/rin/README.md`.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, page_header, section, source_note
from core.storage import read_ts_long
from core.theme import LIGHT_BLUE, NAVY
from pipelines.derived.rin import DENOMINATOR_SERIES, ID_PREFIX, resolve_mandate_twins

CATEGORY_LABELS = {
    "total": "Total renewable fuel",
    "advanced": "Advanced biofuel",
    "biomass_based_diesel": "Biomass-based diesel",
    "cellulosic": "Cellulosic biofuel",
}


def _month(ts: pd.Timestamp) -> str:
    return f"{ts:%b %Y}"


def _mandate_chart(rows: pd.DataFrame) -> go.Figure:
    """Observed solid, projected dashed. The projected trace starts at the last observed
    month so the line is continuous without either segment claiming the other's months."""
    observed = rows[rows["label"] == "observed"]
    projected = rows[rows["label"] == "projected"]
    if not observed.empty and not projected.empty:
        projected = pd.concat([observed.tail(1), projected])

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=observed["ts"], y=observed["value"], mode="lines", name="Observed demand",
            line={"color": NAVY},
        )
    )  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=projected["ts"], y=projected["value"], mode="lines", name="STEO projection",
            line={"color": LIGHT_BLUE, "dash": "dash"},
        )
    )  # fmt: skip
    fig.update_layout(template="kardamow")
    fig.update_yaxes(title_text="Billion RINs per month")
    return fig


def _annual_table(mandate: pd.DataFrame) -> pd.DataFrame:
    frame = mandate.assign(Year=mandate["ts"].dt.year)
    grouped = frame.groupby(["category", "Year"])
    table = pd.DataFrame(
        {
            "Implied mandate, billion RINs": grouped["value"].sum().round(2),
            "Months observed": grouped["label"].apply(lambda s: int((s == "observed").sum())),
            "Months projected": grouped["label"].apply(lambda s: int((s == "projected").sum())),
            "EPA standard": grouped["status"].agg(lambda s: ", ".join(sorted(set(s)))),
        }
    ).reset_index()
    table["Category"] = table["category"].map(CATEGORY_LABELS).fillna(table["category"])
    order = {category: rank for rank, category in enumerate(CATEGORY_LABELS)}
    table = table.sort_values(["category", "Year"], key=lambda c: c.map(order).fillna(c))
    return table[["Category", "Year", *table.columns[2:6]]]


raw = read_ts_long(series_prefix=f"{ID_PREFIX}.", source="derived")
mandate = resolve_mandate_twins(raw)
steo = read_ts_long(
    series_ids=[f"{s}.{label}" for s in DENOMINATOR_SERIES for label in ("observed", "projected")]
)
vintage = None if steo.empty else pd.Timestamp(steo["revision_date"].max()).date()

page_header(
    "RIN Mandate",
    as_of=f"STEO vintage {vintage}" if vintage else None,
    freshness="EIA STEO monthly · EPA standards",
)

if mandate.empty:
    empty_state("derived.rin", "after each STEO pull", None)
    st.info(
        "No implied mandate in the lake. Pull STEO with `python -m pipelines.eia.pull_steo` "
        "(pipelines/eia/pull_steo.py), then build the mandate with "
        "`python -m pipelines.derived.rin`."
    )
    st.stop()

total = mandate[mandate["category"] == "total"].sort_values("ts")
observed_months = total.loc[total["label"] == "observed", "ts"]
projected_months = total.loc[total["label"] == "projected", "ts"]
proposed = mandate[mandate["status"] == "proposed"]

if not observed_months.empty and not projected_months.empty:
    boundary = (
        f"Observed to {_month(observed_months.max())}; "
        f"projected from {_month(projected_months.min())}."
    )
elif projected_months.empty:
    boundary = "Every month shown rests on observed demand."
else:
    boundary = "Every month shown rests on projected demand."

with section("Implied total mandate, monthly"):
    st.plotly_chart(_mandate_chart(total))
    st.caption(
        f"{boundary} A projected month uses STEO's model output for gasoline or distillate "
        "demand; it is not a measurement."
    )
    status_note = (
        "Years "
        + ", ".join(str(y) for y in sorted(proposed["ts"].dt.year.unique()))
        + " use EPA standards that are proposed, not final."
        if not proposed.empty
        else "Every EPA standard used is final."
    )
    source_note(
        "Non-renewable gasoline plus distillate (EIA STEO MGTCPUSX_P + DFTCPUS_P"
        + (f", vintage {vintage}" if vintage else "")
        + f") times EPA's percentage standard. {status_note} One RIN is about one "
        "ethanol-equivalent gallon."
    )

with section("Implied mandate by category and year"):
    st.dataframe(_annual_table(mandate), hide_index=True)
    source_note(
        "Sums of monthly implied mandates. A year with any projected month is partly a "
        "projection; its month counts say how much. Small refinery exemptions, the RIN bank "
        "and actual RIN generation (EPA EMTS) are not included."
    )
