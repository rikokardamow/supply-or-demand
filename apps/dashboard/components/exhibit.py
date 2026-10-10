"""Publishing-layer exhibits, drawn in the app exactly as the published pages draw them.

An exhibit is the dict `apps/artifacts/exhibits.py` builds from the lake: title, stale
flag, two-line takeaway, chart spec and source line. `exhibit()` lays one out with the
app's own primitives -- `section()` heading over a hairline, `source_note()` beneath --
so a chart here, its page, its slide and its worksheet rows all quote the same rows.

`streamlit run` puts apps/dashboard/ on sys.path but not apps/, so the publishing
package is made importable here, once, rather than in every page that wants an exhibit.
"""

from __future__ import annotations

import html
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import streamlit as st
from core.design import MUTED, STATUS_RED, TEXT

from components.lake import CACHE_TTL_SECONDS
from components.section import section, source_note

_APPS = str(Path(__file__).resolve().parents[2])
if _APPS not in sys.path:
    sys.path.append(_APPS)

from artifacts import build, exhibits, figures  # noqa: E402

_FLAG = (
    f"font-size:0.72rem;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;"
    f"color:{STATUS_RED};margin:0 0 0.3rem"
)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_book() -> dict[str, Any]:
    """Every exhibit the lake can support today, plus what it could not build."""
    book = exhibits.build(date.today())
    return {
        "exhibits": book.exhibits,
        "issues": book.issues,
        "meta": build.meta(book, datetime.now(UTC)),
    }


def headline_stats(specs: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """The first `count` headline figures, in the briefing's own running order."""
    by_id = {spec["id"]: spec for spec in specs}
    return [by_id[i]["stat"] for i in exhibits.BRIEFING_ORDER if i in by_id][:count]


def tab_groups(specs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Exhibits grouped under the published dashboard's tab labels; empty tabs dropped."""
    groups = [(label, [s for s in specs if s["tab"] == tab]) for tab, label in exhibits.TABS]
    return [(label, members) for label, members in groups if members]


def exhibit(spec: dict[str, Any]) -> None:
    """One exhibit: heading, stale flag, takeaway, chart, source line."""
    with section(spec["title"]):
        if spec["gap"]:
            st.markdown(
                f'<div style="{_FLAG}">{html.escape(spec["gap"])}</div>',
                unsafe_allow_html=True,
            )
        # Painted as escaped HTML, not markdown: a takeaway quoting "$/bbl" twice would
        # otherwise be read as LaTeX.
        lead, *rest = spec["takeaway"]
        lines = f'<p style="margin:0;color:{TEXT}">{html.escape(lead)}</p>' + "".join(
            f'<p style="margin:0;color:{MUTED}">{html.escape(line)}</p>' for line in rest
        )
        st.markdown(
            f'<div style="font-size:0.87rem;margin:0 0 0.2rem">{lines}</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            figures.figure(spec),
            key=f"exhibit-{spec['id']}",
            config={"displayModeBar": False},
        )
        source_note(spec["source"] + (f" · {spec['note']}" if spec["note"] else ""))
