"""News & Events (Spec 09, Session B; redesigned per a later feature request): a
clickable world map (components/news_map.py) sits above the existing filterable
feed -- clicking a country marker scopes the feed to that country; the existing
commodity/tag/severity/date filters stay and apply on top of the map selection.

Each feed row can be translated (pipelines/news/translate.py, MyMemory-based, cached)
and, once a real ANTHROPIC_API_KEY exists, given a one-sentence "Kardamow take" on
what it could mean for the energy complex (pipelines/news/kardamow_caption.py,
Phase 2 -- gracefully shows an explanatory message instead of crashing until a key
is added, matching this project's own Guardian-key precedent)."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.kardamow_take import kardamow_take
from components.lake import read_events
from components.news_map import render_news_map
from components.section import empty_state, page_header, section
from core.storage import write_events
from core.theme import count_bar_chart
from pipelines.news.kardamow_caption import generate_kardamow_caption
from pipelines.news.newsapi_client import NewsAPIClient
from pipelines.news.pull_news import manual_newsapi_search
from pipelines.news.translate import translate_headline

RANGE_DAYS = {"30D": 30, "90D": 90, "180D": 182, "1Y": 365, "All": None}
FEED_ROW_LIMIT = 30


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


page_header("News & Events")

events = _load_events()
if events.empty:
    empty_state("gdelt", "daily", None)
    st.caption("Run `pipelines/news/pull_news.py` to populate events.")
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

with st.expander("Search NewsAPI (manual — not a scheduled source)"):
    st.caption(
        "One-off manual pull — NewsAPI is not part of the scheduled news ingestion "
        "(see pipelines/news/NOTES.md)."
    )
    search_cols = st.columns([3, 1])
    with search_cols[0]:
        manual_query = st.text_input("Query", key="newsapi_manual_query")
    with search_cols[1]:
        manual_commodity = st.selectbox(
            "Commodity", options=["crude", "gas", "power"], key="newsapi_manual_commodity"
        )
    if st.button("Search", key="newsapi_manual_search_button") and manual_query:
        result = manual_newsapi_search(NewsAPIClient(), manual_query, manual_commodity)
        if result.empty:
            st.info("No articles found for that query.")
        else:
            write_events(result, source="newsapi")
            # Without this the rerun below reads the pre-write cache and the new
            # articles simply don't appear -- for a full hour, with no error to
            # explain it. Any future write path on this page needs the same line.
            read_events.clear()
            st.success(f"Wrote {len(result)} event rows from NewsAPI.")
            st.rerun()

with section("News map"):
    map_key_version = st.session_state.get("news_map_key_version", 0)
    map_event = st.plotly_chart(
        render_news_map(filtered),
        on_select="rerun",
        selection_mode="points",
        key=f"news_map_select_{map_key_version}",
    )
    clicked_points = map_event.selection.points if map_event is not None else []
    if clicked_points:
        # customdata is a per-point [geo] list (see news_map.py) -- Plotly's own
        # click-event JSON indexes a bare string like a list of characters, so a
        # flat customdata array silently truncates to one letter (confirmed live:
        # "United States" came back as "U") unless each point's customdata is
        # itself wrapped in a list.
        st.session_state["events_selected_geo"] = clicked_points[0]["customdata"][0]

    selected_geo = st.session_state.get("events_selected_geo")
    if selected_geo:
        clear_col, label_col = st.columns([1, 5])
        with clear_col:
            if st.button("Clear selection"):
                st.session_state["events_selected_geo"] = None
                # The plotly widget itself remembers its own last selection across
                # reruns (confirmed live: clearing only the session-state variable
                # left the widget re-reporting the same clicked point on the very
                # next rerun, immediately overwriting the clear) -- changing its
                # key forces Streamlit to treat it as a fresh widget with no
                # selection, which is the only way to actually reset it.
                st.session_state["news_map_key_version"] = map_key_version + 1
                st.rerun()
        with label_col:
            st.caption(f"Filtered to **{selected_geo}** — click the button to clear.")

selected_geo = st.session_state.get("events_selected_geo")
if selected_geo:
    filtered = filtered[filtered["geo"] == selected_geo]

with section("Events per week"):
    if filtered.empty:
        st.info("No events match the current filters.")
    else:
        weekly_counts = filtered.set_index("ts")["event_id"].resample("W").count()
        fig = count_bar_chart(weekly_counts, title="Events per week", unit="count")
        st.plotly_chart(fig)

with section(f"News feed ({min(len(filtered), FEED_ROW_LIMIT)} of {len(filtered)} shown)"):
    if filtered.empty:
        st.info("No events match the current filters.")
    else:
        feed_rows = filtered.sort_values("ts", ascending=False).head(FEED_ROW_LIMIT)
        for _, row in feed_rows.iterrows():
            header = f"[{row['commodity']} · severity {row['severity']}] {row['headline']}"
            with st.expander(header):
                st.caption(
                    f"{row['ts']:%Y-%m-%d} · {row['source']} · {row['geo'] or 'unspecified'} "
                    f"· {row['language'] or 'unknown language'} · {row['url']}"
                )
                if st.button("Translate & Kardamow take", key=f"translate_{row['event_id']}"):
                    translated = translate_headline(
                        row["event_id"], row["headline"], row["language"] or ""
                    )
                    st.write(f"**English:** {translated}")
                    try:
                        caption = generate_kardamow_caption(
                            row["event_id"],
                            translated,
                            row["commodity"],
                            row["tags"],
                            row["severity"],
                            row["geo"],
                        )
                        kardamow_take(caption)
                    except RuntimeError as exc:
                        st.info(str(exc))

with section(f"Event table ({len(filtered)} of {len(events)} shown)"):
    st.dataframe(
        filtered[
            ["ts", "commodity", "tags", "severity", "geo", "headline", "source", "url"]
        ].sort_values("ts", ascending=False),
        hide_index=True,
    )
