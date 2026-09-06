"""The component kit is what replaces the bordered card with hairline sections.

AppTest is used rather than a render check because these are Streamlit primitives; the
browser test (-m browser) is what proves they actually paint.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).parent.parent / "apps" / "dashboard"
REPO_ROOT = Path(__file__).parent.parent


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


def test_card_is_an_alias_so_unmigrated_pages_keep_working() -> None:
    """card() delegates to section() during the migration, so the two cannot diverge."""
    at = _run(
        "from components.card import card\n"
        "with card('Legacy Title'):\n"
        "    pass\n"
    )
    assert not at.exception
    assert "Legacy Title" in _text(at)


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


def test_empty_state_says_never_rather_than_none_when_a_source_has_no_data() -> None:
    at = _run(
        "from components.section import empty_state\n"
        "empty_state('aisstream', 'hourly', None)\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "never" in rendered
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


def test_page_header_and_section_paint_real_headings() -> None:
    """Titles must be <h1>/<h2>, not styled <div>s.

    Two things depend on it beyond taste: a screen reader navigating by heading finds
    nothing on a page whose title is a div, and tests/test_pages_browser.py locates every
    page by `h1` with the title text -- so a div title makes a perfectly good page look
    unrendered. The inline style is what carries the Substack's heading face; the tag is
    what carries the document outline.
    """
    at = _run(
        "from components.section import page_header, section\n"
        "page_header('US PADD')\n"
        "with section('Cushing Crude Stocks'):\n"
        "    pass\n"
    )
    assert not at.exception
    rendered = _text(at)
    assert "<h1" in rendered, "page_header must emit an <h1>"
    assert "<h2" in rendered, "section must emit an <h2>"
