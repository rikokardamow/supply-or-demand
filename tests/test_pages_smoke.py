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
