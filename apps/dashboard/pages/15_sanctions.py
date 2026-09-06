"""OFAC SDN Sanctions (Spec 15): four panels over the rolling sanctions table
(pipelines/ofac/pull_ofac.py). Newly-listed energy-related rows also flow into the
existing `events` lake via pipelines/ofac/events_bridge.py -- they already appear on
page 09's map/feed/table and as event-overlay markers on pages 01/02/06, so this
page focuses on the richer sanctions-specific detail that bridge doesn't carry
(full program list, vessel specifics, delisted tracking)."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from components.lake import read_sanctions_current

NEWLY_LISTED_WINDOW_DAYS = 7


def _load_sanctions() -> pd.DataFrame:
    df = read_sanctions_current()
    if df.empty:
        return df
    df = df.copy()
    df["programs"] = df["programs"].map(list)
    return df


st.title("OFAC SDN Sanctions")

sanctions = _load_sanctions()
if sanctions.empty:
    st.info("No sanctions data yet — run `pipelines/ofac/pull_ofac.py`.")
    st.stop()

all_programs = sorted({p for programs in sanctions["programs"] for p in programs})

filter_cols = st.columns(3)
with filter_cols[0]:
    selected_programs = st.multiselect("Program", options=all_programs)
with filter_cols[1]:
    entity_types = st.multiselect(
        "Entity type", options=sorted(sanctions["entity_type"].unique())
    )
with filter_cols[2]:
    energy_only = st.checkbox("Energy-related only", value=False)

filtered = sanctions
if selected_programs:
    filtered = filtered[
        filtered["programs"].map(lambda programs: any(p in programs for p in selected_programs))
    ]
if entity_types:
    filtered = filtered[filtered["entity_type"].isin(entity_types)]
if energy_only:
    filtered = filtered[filtered["energy_related"]]

with card(f"Full SDN table ({len(filtered)} of {len(sanctions)} shown)"):
    st.dataframe(
        filtered[
            ["name", "entity_type", "programs", "energy_related", "status", "first_seen"]
        ].sort_values("first_seen", ascending=False),
        hide_index=True,
    )

with card("Newly listed this week"):
    cutoff = sanctions["first_seen"].max() - pd.Timedelta(days=NEWLY_LISTED_WINDOW_DAYS)
    new_this_week = filtered[filtered["first_seen"] >= cutoff]
    if new_this_week.empty:
        st.info("No new listings in the trailing 7 days.")
    else:
        energy_new = new_this_week[new_this_week["energy_related"]]
        st.caption(
            f"{len(new_this_week)} new listing(s), "
            f"{len(energy_new)} energy-related (highlighted below)."
        )
        st.dataframe(
            new_this_week[["name", "entity_type", "programs", "energy_related", "first_seen"]]
            .sort_values(["energy_related", "first_seen"], ascending=[False, False]),
            hide_index=True,
        )

with card("Vessel watchlist"):
    vessels = filtered[filtered["entity_type"] == "vessel"]
    if vessels.empty:
        st.info("No vessel rows match the current filters.")
    else:
        st.dataframe(
            vessels[["name", "vess_flag", "vess_owner", "programs", "imo"]].sort_values("name"),
            hide_index=True,
        )

with card("Delisted"):
    delisted = filtered[filtered["status"] == "delisted"]
    if delisted.empty:
        st.info("No delisted rows yet.")
    else:
        st.dataframe(
            delisted[["name", "entity_type", "programs", "first_seen", "last_seen"]]
            .sort_values("last_seen", ascending=False),
            hide_index=True,
        )

# Cross-page context: the same OPEC/OPEC+ geographies already tracked on page 06
# (supply) and in Spec 17's Adanos ticker basket (CVX's Venezuela JV, GENL/GKP for
# Iraq, SEPLAT/OANDO/ARADEL for Nigeria) -- see pipelines/ofac/tagging.py's own
# PROGRAM_COUNTRY_PREFIXES for how geo is resolved here.
recent_cutoff = sanctions["first_seen"].max() - pd.Timedelta(days=NEWLY_LISTED_WINDOW_DAYS)
new_this_week_all = sanctions[sanctions["first_seen"] >= recent_cutoff]
opec_prefixes = ("VENEZUELA", "IRAN", "IRAQ", "NIGERIA", "LIBYA")
opec_related = new_this_week_all[
    new_this_week_all["energy_related"]
    & new_this_week_all["programs"].map(
        lambda programs: any(p.upper().startswith(opec_prefixes) for p in programs)
    )
]
kardamow_take(
    f"{len(opec_related)} of this week's energy-related listings tie to "
    "Venezuela, Iran, Iraq, or Libya — the same OPEC/OPEC+ producing geographies "
    "already tracked on the Supply page and in the Adanos sentiment basket's "
    "CVX/GENL/GKP/SEPLAT exposure. A sanctions listing here is real, physical "
    "friction on that country's energy exports, not just headline risk."
)
