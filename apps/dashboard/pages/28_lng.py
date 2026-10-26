"""Atlantic LNG: where US LNG goes, and where Europe's LNG comes from.

What this page must not let a reader miss:

- **Two statistics describe the same cargoes, and they disagree.** EU member states record
  about two-thirds of the LNG the US reports shipping to the EU, a stable ratio, with a
  growing "origin not specified" share. The UK and the US agree closely. Both sides are shown;
  neither is corrected.
- **Europe here is the EU-27 plus the UK, and only LNG from outside Europe counts.**
  Re-exports between European terminals are not new supply.
- **The global view is what countries report to JODI, and gaps are named.** Russia does
  not report its LNG exports. Taiwan files zeros for its imports, and those are treated as
  unreported. Thailand, Bangladesh, Pakistan and Singapore do not report at all. A month
  counts only when its reporters cover 98% of typical volume.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, kpi_row, page_header, section, source_note
from core import gas_projection as gp
from core import lng_balance as lb
from core.design import MA_LONG, MA_MID, MA_SHORT
from core.storage import read_ts_long
from core.theme import GREY, LIGHT_BLUE, NAVY, ORANGE, RED
from pipelines.derived.eu_gas_balance import latest_run

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


def _table(rows: pd.DataFrame, kind: str) -> pd.DataFrame:
    part = rows[(rows["kind"] == kind) & (rows["label"] == "observed")]
    return part.pivot(index="ts", columns="name", values="value").sort_index()


def _stacked(table: pd.DataFrame, colours: dict[str, str], labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for key, colour in colours.items():
        if key in table and table[key].abs().sum() > 0:
            fig.add_trace(
                go.Bar(x=table.index, y=table[key], name=labels[key], marker_color=colour)
            )
    fig.update_layout(template="kardamow", barmode="relative")
    fig.update_yaxes(title_text="bcm per month")
    return fig


def _mirror_chart(eu: pd.DataFrame, uk: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for frame, name, colour in ((eu, "EU", NAVY), (uk, "UK", ORANGE)):
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
    return fig


derived = latest_run(read_ts_long(series_prefix="derived.lng.", source="derived"))
if derived.empty:
    page_header("LNG", freshness="EIA monthly · Eurostat monthly · DESNZ monthly")
    empty_state("derived.lng", "monthly", None)
    st.info(
        "No LNG model in the lake. Run `python -m pipelines.eia.pull_lng_exports`, "
        "`python -m pipelines.eurostat_gas.pull`, `python -m pipelines.desnz_gas.pull`, then "
        "`python -m pipelines.derived.lng`."
    )
    st.stop()

us = _table(derived, "us_exports")
europe = _table(derived, "europe_imports")
mirror_eu = _table(derived, "mirror_eu")
mirror_uk = _table(derived, "mirror_uk")

page_header(
    "LNG",
    as_of=f"EIA to {us.index.max():%b %Y} · Europe to {europe.index.max():%b %Y}",
    freshness="EIA · Eurostat · DESNZ, monthly",
)

us12 = us.tail(12)
eu12 = europe.tail(12)
kpi_row(
    [
        ("US LNG exports, 12m", f"{us12.sum().sum():.1f} bcm", None),
        ("Share to Europe", f"{us12['europe'].sum() / us12.sum().sum() * 100:.0f} %", None),
        ("Europe LNG imports, 12m", f"{eu12.sum().sum():.1f} bcm", None),
        (
            "US share of Europe's LNG",
            f"{eu12['united_states'].sum() / eu12.sum().sum() * 100:.0f} %",
            None,
        ),
    ]
)
st.caption(
    f"US: twelve months to {us12.index.max():%b %Y}. Europe: twelve months to "
    f"{eu12.index.max():%b %Y}. Europe's share uses European statistics (see the last section)."
)

with section("US LNG exports by destination region"):
    st.plotly_chart(_stacked(us.loc["2019":], REGION_COLOURS, lb.REGIONS))
    source_note(
        "EIA natural-gas/move/expc, exports by vessel and by truck, per destination; they add up "
        "to EIA's national total in every month since 2017. Region mapping: "
        "pipelines/derived/lng/destinations.csv."
    )

with section("Europe's LNG imports by origin"):
    st.plotly_chart(_stacked(europe.loc["2019":], ORIGIN_COLOURS, lb.ORIGINS))
    annual = gp.calendar_year(europe).loc[2019:].rename(columns=lb.ORIGINS)
    st.dataframe(annual.T.round(1), width="stretch")
    source_note(
        "EU-27 (Eurostat nrg_ti_gasm, LNG) plus UK (DESNZ ET 4.3, LNG), imports from outside "
        "Europe only; months both publish. A year missing any month is blank."
    )

with section("The same cargoes in two statistics"):
    st.plotly_chart(_mirror_chart(mirror_eu, mirror_uk))
    eu_years = gp.calendar_year(mirror_eu).dropna()
    if not eu_years.empty:
        ratio = (eu_years["europe_reported"] / eu_years["us_reported"]).loc[2021:]
        st.caption(
            "EU statistics record "
            + ", ".join(f"{y} {r * 100:.0f}%" for y, r in ratio.items())
            + " of the LNG the US reports shipping to the EU. Part of the gap is cargo the EU "
            "books as 'origin not specified'. Part is likely cargo recorded against a transit "
            "or trading country. A cargo in transit at a month end shifts a month, not a year."
        )
    source_note("US side: EIA exports to EU members and to the UK. Europe side: Eurostat, DESNZ.")

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

world_exports = _table(derived, "global_exports")
world_imports = _table(derived, "global_imports")
if world_exports.empty or world_imports.empty:
    st.info(
        "No global LNG view: run `python -m pipelines.jodi_gas.pull` (needs JODI_USERNAME and "
        "JODI_PASSWORD in .env), then `python -m pipelines.derived.lng`."
    )
else:
    with section("Global LNG: exporters and importers"):
        imp12 = world_imports.tail(12)
        kpi_row(
            [
                (f"{lb.GROUP_LABELS[k]}, 12m", f"{imp12[k].sum():.1f} bcm", None)
                for k in ("china", "japan", "south_korea", "india")
            ]
        )
        st.caption(f"LNG imports, twelve months to {imp12.index.max():%b %Y}.")
        st.plotly_chart(_stacked(world_exports.loc["2019":], EXPORTER_COLOURS, lb.GROUP_LABELS))
        st.plotly_chart(_stacked(world_imports.loc["2019":], IMPORTER_COLOURS, lb.GROUP_LABELS))
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
        st.dataframe(years.round(1), width="stretch")
        st.caption(
            f"Exports complete to {world_exports.index.max():%b %Y}, imports to "
            f"{world_imports.index.max():%b %Y}: later months are still being reported and "
            "are left out rather than shown as a fall. Reported exports and imports do not "
            "match: Russia's exports are missing, several importers do not report, and cargoes "
            "at sea cross month ends."
        )
        source_note(
            "JODI-Gas World Database via the JODI REST API, NATGAS flows EXPLNG and IMPLNG, "
            "million m3. Europe here also includes Türkiye. Groups: core/lng_balance.py."
        )
