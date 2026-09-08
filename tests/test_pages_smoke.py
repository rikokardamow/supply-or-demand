"""Headless smoke test for every dashboard page (Spec 13 Session B).

Real, confirmed-live gotcha: AppTest.from_file() on a page file directly (e.g.
"apps/dashboard/pages/09_events.py") raises ModuleNotFoundError: No module named
'components' -- apps/dashboard/ isn't on sys.path the way `streamlit run` puts it
there. The documented, working pattern (from AppTest.from_file's own docstring)
is to load the app's entrypoint once and switch_page into each page from there."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "apps" / "dashboard" / "pages"
APP_ENTRYPOINT = REPO_ROOT / "apps" / "dashboard" / "app.py"
PAGE_FILES = sorted(p.name for p in PAGES_DIR.glob("*.py"))


@pytest.mark.parametrize("page_file", PAGE_FILES)
def test_page_loads_without_raising(page_file: str) -> None:
    at = AppTest.from_file(str(APP_ENTRYPOINT)).run(timeout=30)
    at = at.switch_page(f"pages/{page_file}").run(timeout=30)

    assert not at.exception, f"{page_file} raised: {at.exception}"


def test_every_page_keeps_its_current_url_slug() -> None:
    """st.navigation replaces filename-derived routing, so each page must declare the
    slug it already had.

    tests/test_pages_browser.py selects nav links by these slugs, and any bookmark uses
    them. Omitting url_path lets Streamlit re-derive routes from the declared titles,
    which silently renames every page's URL -- a break with no error attached.

    Read from nav.PAGES' plain specs rather than from st.Page objects: st.Page needs a
    live ScriptRunContext to finish initialising, so asserting on its .url_path passes
    or fails depending on whether an earlier AppTest happened to leave a context behind.
    """
    import re
    import sys

    sys.path.insert(0, str(REPO_ROOT / "apps" / "dashboard"))
    import nav

    specs = [spec for group in nav.PAGES.values() for spec in group]

    assert [spec.url_path for spec in specs if spec.default] == ["home"], (
        "exactly one page may be default, and it must be home: Streamlit serves the "
        "default page at the root URL, where app.py's body used to render."
    )
    assert {spec.file for spec in specs} == set(PAGE_FILES), (
        "nav.PAGES and pages/ have drifted -- a page file with no nav entry is "
        "unreachable, and an entry with no file raises at startup."
    )

    slug_re = re.compile(r"[0-9]*[_ -]*(.*)\.py")
    expected = set()
    for name in PAGE_FILES:
        match = slug_re.fullmatch(name)
        assert match, f"{name} doesn't match Streamlit's page filename pattern"
        expected.add(re.sub(r"[_ ]+", "_", match.group(1)).strip("_"))

    assert {spec.url_path for spec in specs} == expected
