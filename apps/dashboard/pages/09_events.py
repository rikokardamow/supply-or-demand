"""News & Events (Spec 09, Session B): filterable event table (commodity/tag/
severity/date) + an events-per-week volume bar chart. Overlaying event markers onto
other pages' charts (01/02/07) is Session C's job, not built here."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.card import card
from core.storage import read_events
from core.theme import count_bar_chart

RANGE_DAYS = {"30D": 30, "90D": 90, "180D": 182, "1Y": 365, "All": None}


def _load_events() -> pd.DataFrame:
    df = read_events()
    if df.empty:
        return df
    df = df.copy()
    # DuckDB hands back a list-typed column as a numpy array per row, not a plain
    # Python list (confirmed live, see pipelines/news/NOTES.md) -- normalise once
    # here so every downstream filter/display can treat `tags` as a real list.
    df["tags"] = df["tags"].map(list)
    return df


st.title("News & Events")

events = _load_events()
if events.empty:
    st.info("No events yet — run `pipelines/news/pull_news.py`.")
    st.stop()

range_label = st.segmented_control(
    "Time range",
    options=list(RANGE_DAYS),
    default="90D",
    required=True,
    key="events_range",
)
days = RANGE_DAYS[range_label]
if days is not None:
    cutoff = events["ts"].max() - pd.Timedelta(days=days)
    events = events[events["ts"] >= cutoff]

all_tags = sorted({tag for tags in events["tags"] for tag in tags})

filter_cols = st.columns(3)
with filter_cols[0]:
    commodities = st.multiselect("Commodity", options=sorted(events["commodity"].unique()))
with filter_cols[1]:
    selected_tags = st.multiselect("Tag", options=all_tags)
with filter_cols[2]:
    min_severity = st.selectbox("Min severity", options=[1, 2, 3], index=0)

filtered = events
if commodities:
    filtered = filtered[filtered["commodity"].isin(commodities)]
if selected_tags:
    filtered = filtered[
        filtered["tags"].map(lambda tags: any(t in tags for t in selected_tags))
    ]
filtered = filtered[filtered["severity"] >= min_severity]

with card("Events per week"):
    if filtered.empty:
        st.info("No events match the current filters.")
    else:
        weekly_counts = filtered.set_index("ts")["event_id"].resample("W").count()
        fig = count_bar_chart(weekly_counts, title="Events per week", unit="count")
        st.plotly_chart(fig, use_container_width=True)

with card(f"Event table ({len(filtered)} of {len(events)} shown)"):
    st.dataframe(
        filtered[
            ["ts", "commodity", "tags", "severity", "geo", "headline", "source", "url"]
        ].sort_values("ts", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
