"""Kardamow supply-demand models as a Plotly Dash app.

    uv run python apps/dash_app/app.py                       # from the repo root
    DASHBOARD_LAKE=/path/to/data/lake uv run python apps/dash_app/app.py

Serves http://127.0.0.1:8050 with the EU gas, UK gas, EU carbon and LNG pages. Each page
is built by ``apps/dashboard/views/sd.py``, the same views the Streamlit pages 25-28
render, and reads the lake fresh on every navigation. ``DASHBOARD_LAKE`` points the app at
a lake outside this checkout (a local setting; the default is ``data/lake``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
# Same arrangement as `streamlit run` and tests/test_pages_smoke.py: the views live in
# apps/dashboard/ and import from the repo root.
for path in (REPO_ROOT, REPO_ROOT / "apps" / "dashboard", REPO_ROOT / "apps"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core import storage  # noqa: E402
from core.design import BODY_STACK, BODY_URL, HEADING_STACK, HEADING_URL, RULE, TEXT  # noqa: E402
from dash import Dash, Input, Output, dcc, html  # noqa: E402
from views.sd import VIEWS  # noqa: E402

from dash_app.render import render  # noqa: E402

if os.environ.get("DASHBOARD_LAKE"):
    storage.LAKE_ROOT = Path(os.environ["DASHBOARD_LAKE"])

PAGES: dict[str, str] = {
    "eu_gas_balance": "EU Gas Balance",
    "uk_gas_balance": "UK Gas Balance",
    "eu_carbon": "EU Carbon",
    "lng": "LNG",
}
DEFAULT_PAGE = "eu_gas_balance"


def page_layout(pathname: str | None) -> Any:
    """The layout for a URL path. Unknown paths fall back to the first page."""
    slug = (pathname or "").strip("/") or DEFAULT_PAGE
    if slug not in VIEWS:
        slug = DEFAULT_PAGE
    return render(VIEWS[slug]())


def _nav() -> html.Nav:
    links = [
        dcc.Link(
            title,
            href=f"/{slug}",
            style={"margin": "0 0.9rem", "color": TEXT, "textDecoration": "none"},
        )
        for slug, title in PAGES.items()
    ]
    return html.Nav(links, style={"textAlign": "center", "fontSize": "0.95rem", "margin": "0.4rem"})


def create_app() -> Dash:
    app = Dash(
        __name__,
        title="Kardamow Energy Dashboard",
        external_stylesheets=[HEADING_URL, BODY_URL],
        suppress_callback_exceptions=True,
    )
    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            html.H1(
                "Kardamow",
                style={
                    "textAlign": "center",
                    "fontFamily": HEADING_STACK,
                    "fontSize": "3.25rem",
                    "fontWeight": 600,
                    "color": TEXT,
                    "margin": "0",
                    "padding": "0.4rem 0 0.7rem",
                },
            ),
            html.Hr(style={"border": "0", "borderTop": f"1px solid {RULE}", "margin": "0"}),
            _nav(),
            html.Div(
                id="page", style={"maxWidth": "1200px", "margin": "0 auto", "padding": "0 1rem"}
            ),
        ],
        style={"fontFamily": BODY_STACK, "color": TEXT, "background": "#ffffff"},
    )
    app.callback(Output("page", "children"), Input("url", "pathname"))(page_layout)
    return app


if __name__ == "__main__":
    create_app().run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT", "8050")))
