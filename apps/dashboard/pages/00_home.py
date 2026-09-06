"""Home — lake status at a glance. Reads the lake, never calls APIs directly.

Was apps/dashboard/app.py's body until the 2026-09-06 restyle. Under st.navigation the
entrypoint renders chrome and runs the selected page, so home content cannot live there
-- it would paint on every page.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from components.section import kpi_row, page_header, section
from core.freshness import staleness_report

_STATUS_ORDER = {"red": 0, "amber": 1, "green": 2}
_STATUS_LABEL = {"red": "Stale", "amber": "Ageing", "green": "Current"}

# Shorter than the ttl=3600 the analytics pages use. Those cache expensive model fits over
# data that only changes on a pull; this is a *status* panel, and one that keeps insisting
# a source is stale for an hour after the pull that fixed it is worse than useless. Five
# minutes still collapses the many reruns of a single browsing session into one query.
_STATUS_TTL_SECONDS = 300


@st.cache_data(ttl=_STATUS_TTL_SECONDS)
def _lake_status() -> pd.DataFrame:
    """Cached because Streamlit reruns this whole script on every interaction, and an
    uncached staleness_report() meant re-querying the lake each time."""
    return staleness_report()


report = _lake_status()
report = report.sort_values(
    by="status", key=lambda col: col.map(_STATUS_ORDER)
).reset_index(drop=True)
counts = report["status"].value_counts()
# A word beside the count, not a coloured dot alone: status must never be carried by
# colour by itself.
report["status"] = [_STATUS_LABEL[s] for s in report["status"]]

page_header(
    "Energy Dashboard",
    as_of=pd.Timestamp.now(tz="UTC").strftime("%d %b %Y").upper(),
    freshness=f"{len(report)} sources tracked",
)
kpi_row(
    [
        ("Sources", str(len(report)), None),
        ("Stale", str(int(counts.get("red", 0))), None),
        ("Ageing", str(int(counts.get("amber", 0))), None),
        ("Current", str(int(counts.get("green", 0))), None),
    ]
)

with section("Lake status"):
    st.caption(
        "Every source across ts_long, flows, events and sanctions, checked against its "
        "own expected pull cadence (see core/freshness.py) — Current is within cadence, "
        "Ageing is up to 2x cadence, Stale is beyond that."
    )
    st.dataframe(report, hide_index=True)
