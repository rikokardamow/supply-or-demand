"""Briefing — the publishing layer's exhibits, in the app.

The same exhibit specs that feed the published pages, the PowerPoint briefing and the
Excel workbook (`apps/artifacts/`), so this page and those files cannot disagree. Read
from the lake only; a stale or missing series is flagged, never filled.
"""

from __future__ import annotations

import streamlit as st
from components.exhibit import exhibit, headline_stats, load_book, tab_groups
from components.section import empty_state, kpi_row, page_header, section

HEADLINE_COUNT = 4

book = load_book()
specs = book["exhibits"]
meta = book["meta"]

page_header(
    "Briefing",
    as_of=f"Pipeline as-of {meta['newest_run'] or 'not recorded'}",
    freshness=f"{meta['stale']} of {meta['exhibits']} exhibits stale",
)

if not specs:
    empty_state("lake", "per source cadence", None)
else:
    kpi_row(
        [
            (
                stat["label"],
                f"{stat['value']} {stat['unit']}",
                f"{stat['delta']} {stat['delta_label']}" if stat["delta"] else None,
            )
            for stat in headline_stats(specs, HEADLINE_COUNT)
        ]
    )

    indicators = st.toggle("Moving averages (MA20, MA100, MA200)", value=False)
    groups = tab_groups(specs)
    for tab, (_, members) in zip(st.tabs([label for label, _ in groups]), groups, strict=True):
        with tab:
            columns = st.columns(2, gap="large")
            for i, spec in enumerate(members):
                with columns[i % 2]:
                    exhibit(spec, indicators=indicators)

if book["issues"]:
    with section("Not built"):
        for issue in book["issues"]:
            st.caption(issue)
