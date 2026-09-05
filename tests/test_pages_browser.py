"""Real-browser render check for every dashboard page (follow-up to Spec 13's
`tests/test_pages_smoke.py`).

Real gap that AppTest can't see: `test_pages_smoke.py` only proves the Python script
didn't raise -- it says nothing about whether the browser actually painted anything.
A chart that fails client-side (e.g. Plotly choking on a shape it was never built to
handle) or a card that silently ends up empty renders as a blank pane with no Python
exception at all. This test drives a real headless Chromium against a real
`streamlit run` process and checks that each page's own `st.title()` text is visible,
that more than just the title got rendered, and that the browser logged no console
errors while painting it.

Opt-in only (`pytest -m browser`) -- excluded from the default run by pyproject.toml's
addopts, since it needs `playwright install chromium` (one-off, not part of `uv sync`)
and is far slower than the rest of the suite (spins up a real Streamlit server and
renders every page against the real lake, including the cartopy/matplotlib weather
maps)."""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests
from playwright.sync_api import ConsoleMessage, Page, sync_playwright

pytestmark = pytest.mark.browser

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "apps" / "dashboard" / "pages"
APP_ENTRYPOINT = "apps/dashboard/app.py"
HOME_TITLE = "Kardamow Energy Dashboard"

_TITLE_RE = re.compile(r'st\.title\(\s*["\'](.+?)["\']')

# Same shape as Streamlit's own PAGE_FILENAME_REGEX (streamlit/source_util.py) -- confirmed
# live that Streamlit's sidebar nav order is NOT a lexical filename sort (it sorts by
# (float(leading_number), label), so e.g. "015_us_oil_overview.py" ties numerically with
# "15_sanctions.py" rather than sorting lexically-first) -- so a positional nav-link index
# built from sorted(glob(...)) clicks the wrong page for most of these files. Selecting by
# this slug instead (it becomes the nav link's href suffix) sidesteps ordering entirely.
_SLUG_RE = re.compile(r"[0-9]*[_ -]*(.*)\.py")


def _page_title(page_file: Path) -> str:
    match = _TITLE_RE.search(page_file.read_text(encoding="utf-8"))
    assert match, f"{page_file.name} has no st.title(...) call to check against"
    return match.group(1)


def _page_slug(page_file: Path) -> str:
    match = _SLUG_RE.fullmatch(page_file.name)
    assert match, f"{page_file.name} doesn't match Streamlit's own page filename pattern"
    return re.sub(r"[_ ]+", "_", match.group(1)).strip("_")


PAGE_SLUGS_AND_TITLES = [(_page_slug(p), _page_title(p)) for p in sorted(PAGES_DIR.glob("*.py"))]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("localhost", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, proc: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"streamlit process exited early (code {proc.returncode}):\n"
                f"{proc.stdout.read() if proc.stdout else ''}"
            )
        try:
            if requests.get(f"{base_url}/_stcore/health", timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"streamlit server never became healthy within {timeout}s")


@pytest.fixture(scope="module")
def streamlit_server() -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            APP_ENTRYPOINT,
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=localhost",
            "--server.runOnSave=false",
            "--browser.gatherUsageStats=false",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base_url = f"http://localhost:{port}"
        _wait_for_health(base_url, proc, timeout=60)
        # /_stcore/health only proves the HTTP server is bound -- it says nothing about
        # whether the main script's own (heavy: cartopy, xarray, matplotlib,
        # ecmwf-opendata, ib_async, gridstatus, ...) import chain has finished, which
        # happens lazily on the first real session. Confirmed live: without this warm-up,
        # the very first browser navigation below can outrun a 45s render timeout even
        # though every subsequent (warm) page loads comfortably inside it.
        requests.get(base_url, timeout=120)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser_page() -> Iterator[tuple[Page, list[str]]]:
    console_errors: list[str] = []

    def _on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", _on_console)
        yield page, console_errors
        browser.close()


def _assert_page_rendered(page: Page, title: str, console_errors: list[str]) -> None:
    page.wait_for_load_state("networkidle", timeout=45_000)
    page.locator("h1", has_text=title).wait_for(state="visible", timeout=45_000)

    assert not console_errors, f"{title}: browser console logged errors: {console_errors}"
    assert page.locator('[data-testid="stException"]').count() == 0, f"{title}: exception shown"

    # More than the title alone must have painted -- a page that renders just the
    # <h1> and nothing else is exactly the "loads but shows nothing" bug AppTest
    # can't see (e.g. every card silently short-circuits on an empty dataframe).
    # Confirmed live: Streamlit streams the title in an early delta and the rest of the
    # page (e.g. the home page's "Lake status" card, which reads several lake datasets)
    # in a later one over the same session -- a one-shot count right after the title
    # becomes visible is a real race, not a rendering bug. Poll instead.
    containers = page.locator('[data-testid="stAppViewContainer"] .element-container')
    deadline = time.monotonic() + 20
    while containers.count() <= 1 and time.monotonic() < deadline:
        page.wait_for_timeout(250)
    assert containers.count() > 1, f"{title}: only the title rendered, no chart/card content"


def test_home_page_renders(streamlit_server: str, browser_page: tuple[Page, list[str]]) -> None:
    page, console_errors = browser_page
    page.goto(streamlit_server, timeout=30_000)
    _assert_page_rendered(page, HOME_TITLE, console_errors)


@pytest.mark.parametrize(
    "slug,title", PAGE_SLUGS_AND_TITLES, ids=[p[0] for p in PAGE_SLUGS_AND_TITLES]
)
def test_page_renders_in_browser(
    streamlit_server: str,
    browser_page: tuple[Page, list[str]],
    slug: str,
    title: str,
) -> None:
    page, console_errors = browser_page

    # Navigate only when the browser isn't already on the app. Without any navigation at
    # all, every case here is order-dependent: selecting a single one (`-k cracks`, or a
    # specific node id) never requests the `streamlit_server` fixture, so no server
    # starts, the page is still about:blank, and the sidebar-nav click times out after
    # 30s against a locator that cannot exist -- which made a perfectly green page look
    # broken. Navigating *unconditionally* is the wrong fix: each `goto` starts a fresh
    # Streamlit session and re-runs the whole app, and doing that 15 times pushed the
    # three heavy trading pages over their render timeouts. Conditional navigation keeps
    # the fast warm path for a full-module run and still makes each case self-contained.
    if not page.url.startswith(streamlit_server):
        page.goto(streamlit_server, timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=45_000)
    console_errors.clear()

    page.locator(f'[data-testid="stSidebarNav"] a[href$="/{slug}"]').click()

    _assert_page_rendered(page, title, console_errors)
