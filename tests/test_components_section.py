"""The component kit is what replaces the bordered card with hairline sections.

AppTest is used rather than a render check because these are Streamlit primitives; the
browser test (-m browser) is what proves they actually paint.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).parent.parent / "apps" / "dashboard"
REPO_ROOT = Path(__file__).parent.parent


class _HeadingAttrs(HTMLParser):
    """Collects the attributes of the first `tag` start-tag a real browser would see.

    Using html.parser rather than a substring check matters: it is the only way to
    reproduce the single-quote defect, where an attribute value containing a single
    quote (HEADING_STACK's "'Times New Roman'") terminates the attribute early and the
    rest of the declaration is parsed as bare, stray attributes.
    """

    def __init__(self, tag: str) -> None:
        super().__init__()
        self._tag = tag
        self.attrs: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == self._tag and self.attrs is None:
            self.attrs = dict(attrs)


def _find_heading_attrs(html_fragment: str, tag: str) -> dict[str, str | None]:
    parser = _HeadingAttrs(tag)
    parser.feed(html_fragment)
    assert parser.attrs is not None, f"no <{tag}> found in {html_fragment!r}"
    return parser.attrs


def _run(body: str) -> AppTest:
    """Run a snippet with apps/dashboard importable, the way `streamlit run` has it."""
    preamble = (
        "import sys\n"
        f"sys.path.insert(0, {str(DASHBOARD)!r})\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
    )
    return AppTest.from_string(preamble + body).run(timeout=30)


def _text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_section_renders_its_title_once() -> None:
    at = _run(
        "from components.section import section\n"
        "with section('Cushing Crude Stocks'):\n"
        "    pass\n"
    )
    assert not at.exception
    assert "Cushing Crude Stocks" in _text(at)


def test_empty_state_names_the_source_and_its_cadence() -> None:
    at = _run(
        "from components.section import empty_state\n"
        "empty_state('entsog', 'daily', '2026-08-30')\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "entsog" in rendered
    assert "daily" in rendered
    assert "2026-08-30" in rendered


def test_empty_state_says_not_tracked_rather_than_none_when_a_source_has_no_data() -> None:
    at = _run(
        "from components.section import empty_state\n"
        "empty_state('aisstream', 'hourly', None)\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "not tracked" in rendered
    assert "None" not in rendered


def test_page_header_renders_title_and_meta() -> None:
    at = _run(
        "from components.section import page_header\n"
        "page_header('US PADD', as_of='SEP 3', freshness='2 of 9 sources stale')\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "US PADD" in rendered
    assert "SEP 3" in rendered
    assert "2 of 9 sources stale" in rendered


def test_page_header_omits_the_meta_line_when_there_is_no_meta() -> None:
    at = _run(
        "from components.section import page_header\n"
        "page_header('Supply')\n"
    )
    assert not at.exception
    assert "Supply" in _text(at)


def test_kpi_row_renders_one_metric_per_item() -> None:
    at = _run(
        "from components.section import kpi_row\n"
        "kpi_row([('Sources', '23', None), ('Stale', '7', '+2')])\n"
    )
    assert not at.exception
    assert len(at.metric) == 2


def test_kpi_row_tolerates_an_empty_list() -> None:
    """A page with nothing to headline must not crash on st.columns(0)."""
    at = _run("from components.section import kpi_row\nkpi_row([])\n")
    assert not at.exception


def test_source_note_renders_its_text() -> None:
    at = _run(
        "from components.section import source_note\n"
        "source_note('EIA WCESTUS1 · thousand barrels')\n"
    )
    assert not at.exception
    assert "WCESTUS1" in _text(at)


@pytest.mark.parametrize(
    ("tag", "snippet"),
    [
        (
            "h3",
            "from components.section import section\n"
            "with section('Cushing Crude Stocks'):\n"
            "    pass\n",
        ),
        (
            "h2",
            "from components.section import page_header\n"
            "page_header('Some Title')\n",
        ),
    ],
    ids=["section-h3", "page_header-h2"],
)
def test_heading_style_attribute_survives_html_parsing(tag: str, snippet: str) -> None:
    """A single-quoted style attribute is silently discarded by a real browser.

    HEADING_STACK is "Lora, Georgia, 'Times New Roman', serif" -- it contains single
    quotes. Emitting the style attribute itself in single quotes
    (style='font-family:...'Times New Roman'...') terminates the attribute at the
    quote before "Times"; the browser then parses "times" and "new" as bare, stray
    attributes and throws away everything after them, including font-size. A test
    that merely greps the markdown string for "font-family" cannot see this -- it has
    to parse the markup as a browser does.

    Parametrized over both headings that interpolate HEADING_STACK the same way --
    section()'s <h3> and page_header()'s <h2> -- so a fix to only one of the two
    still fails this test.
    """
    at = _run(snippet)
    assert not at.exception
    rendered = _text(at)
    attrs = _find_heading_attrs(rendered, tag)
    style = attrs.get("style")
    assert style is not None, f"style attribute was lost to HTML parsing; got {attrs}"
    assert "font-family" in style
    assert "font-size" in style
    assert "times" not in attrs
    assert "new" not in attrs


def test_page_header_and_section_paint_real_headings() -> None:
    """Titles must be <h2>/<h3>, not styled <div>s.

    Two things depend on it beyond taste: a screen reader navigating by heading finds
    nothing on a page whose title is a div, and tests/test_pages_browser.py locates every
    page by its title's heading level -- so a div title makes a perfectly good page look
    unrendered. The inline style is what carries the Substack's heading face; the tag is
    what carries the document outline. <h1> is reserved for the "Kardamow" wordmark
    painted once in apps/dashboard/app.py, so page_header() and section() sit one level
    lower each: <h2> and <h3>.
    """
    at = _run(
        "from components.section import page_header, section\n"
        "page_header('US PADD')\n"
        "with section('Cushing Crude Stocks'):\n"
        "    pass\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "<h2" in rendered, "page_header must emit an <h2>"
    assert "<h3" in rendered, "section must emit an <h3>"
