"""The publication's layout primitives -- hairline rules and whitespace, never boxes.

Replaces the bordered card() the dashboard used before the 2026-09-06 restyle, matching
kardamow.substack.com: a section is a label over a hairline rule, meta lines are
letterspaced grey caps, and nothing is boxed.

Headings are painted here rather than with st.subheader so they carry the heading stack
from core/design.py -- including its Georgia/serif fallback, which Streamlit's own
generated font chain does not have. They are still real heading tags: the inline style
carries the face, the tag carries the document outline that screen readers navigate by
(and that tests/test_pages_browser.py locates each page with). The document's only <h1>
is the "Kardamow" wordmark painted in apps/dashboard/app.py; page_header() paints <h2>
and section() paints <h3>, so every page keeps a single, valid descending outline.
padding:0 is not decoration -- Streamlit's own heading rules add vertical padding these
margins assume away.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import streamlit as st
from core.design import HEADING_STACK, MUTED, RULE, TEXT

_META = f"font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};"
_RULE = f'<hr style="border:0;border-top:1px solid {RULE};margin:{{margin}}">'


@contextmanager
def section(title: str) -> Iterator[None]:
    """A titled content block: heading, hairline rule, then the caller's content.

    The section owns the title. Chart builders in core/theme.py deliberately no longer
    paint one -- before the restyle both did, and the chart's was clipped at the card
    edge and overlapped the legend.
    """
    st.markdown(
        f'<h3 style="font-family:{HEADING_STACK};font-size:1.05rem;font-weight:600;'
        f'color:{TEXT};text-align:center;margin:1.6rem 0 0.15rem;padding:0">{title}</h3>'
        + _RULE.format(margin="0 0 0.9rem"),
        unsafe_allow_html=True,
    )
    yield


def page_header(
    title: str, as_of: str | None = None, freshness: str | None = None
) -> None:
    """Page title in the heading face, with the Substack's caps meta line beneath."""
    st.markdown(
        f'<h2 style="font-family:{HEADING_STACK};font-size:2.1rem;font-weight:600;'
        f'color:{TEXT};text-align:center;margin:0.2rem 0 0.35rem;padding:0">{title}</h2>',
        unsafe_allow_html=True,
    )
    meta = " · ".join(part for part in (as_of, freshness) if part)
    if meta:
        st.markdown(f'<div style="{_META}">{meta}</div>', unsafe_allow_html=True)
    st.markdown(_RULE.format(margin="0.8rem 0 1.4rem"), unsafe_allow_html=True)


def kpi_row(items: Sequence[tuple[str, str, str | None]]) -> None:
    """A strip of headline numbers: (label, value, delta-or-None) per column."""
    if not items:
        return  # st.columns(0) raises; a page with nothing to headline is legitimate
    for column, (label, value, delta) in zip(st.columns(len(items)), items, strict=True):
        with column:
            st.metric(label, value, delta)


def empty_state(source: str, cadence: str, last_seen: str | None) -> None:
    """Deliberate NO-DATA rendering. Pages show absence rather than hiding it."""
    seen = last_seen or "never"
    st.markdown(
        f'<div style="{_META}padding:1.6rem 0">No data · {source} · '
        f"expected {cadence} · last seen {seen}</div>",
        unsafe_allow_html=True,
    )


def source_note(text: str) -> None:
    """Grey caps footnote under a chart -- provenance, units, caveats."""
    st.markdown(
        f'<div style="{_META}margin-top:-0.4rem">{text}</div>', unsafe_allow_html=True
    )
