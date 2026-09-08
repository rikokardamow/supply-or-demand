"""Explicit page registry for st.navigation (2026-09-06 restyle).

Streamlit's pages/ auto-discovery gave lowercase filename labels in a flat sidebar
("app", "us padd", "eu gas flows") ordered by leading number. st.navigation lets the
labels, the order and the grouping be deliberate -- at the cost of declaring every page
here, which is the trade this makes.

The registry is plain data, and st.Page objects are built only inside build(). That is
deliberate: st.Page's constructor reads the active ScriptRunContext to resolve its file
against the main script, and outside a script run it returns a half-built object whose
.url_path raises AttributeError. Holding st.Page in a module-level dict therefore made
the registry readable only from inside a running app -- tests appeared to pass only
because an earlier AppTest had leaked a context onto the thread, and failed when run
alone. Plain specs are readable anywhere, which is what both page tests need.

url_path is mandatory on every entry. Without it Streamlit re-derives routes from the
declared titles, which silently changes every page's URL: bookmarks break, and
tests/test_pages_browser.py's slug-based nav-link selectors break with it. Note that
Streamlit serves the default page at the root URL, so the home entry's declared "home"
is what this file records while st.Page.url_path reports "" for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

_P = "pages/"


@dataclass(frozen=True)
class PageSpec:
    """One nav entry: the page file, how it is labelled, and where it is served."""

    file: str
    title: str
    url_path: str
    default: bool = False


PAGES: dict[str, tuple[PageSpec, ...]] = {
    "Overview": (
        PageSpec("00_home.py", "Home", "home", default=True),
        PageSpec("015_us_oil_overview.py", "US Oil Overview", "us_oil_overview"),
        PageSpec("09_events.py", "Events", "events"),
    ),
    "Fundamentals": (
        PageSpec("01_us_padd.py", "US PADD", "us_padd"),
        PageSpec("02_gas_storage.py", "Gas Storage", "gas_storage"),
        PageSpec("03_eu_gas_flows.py", "EU Gas Flows", "eu_gas_flows"),
        PageSpec("04_eu_power.py", "EU Power", "eu_power"),
        PageSpec("05_us_gas_power.py", "US Gas & Power", "us_gas_power"),
        PageSpec("06_supply.py", "Supply", "supply"),
        PageSpec("08_weather.py", "Weather", "weather"),
        PageSpec("19_fundamentals.py", "Fundamentals", "fundamentals"),
    ),
    "Trading": (
        PageSpec("18_curve.py", "Curve", "curve"),
        PageSpec("20_cracks.py", "Cracks", "cracks"),
        PageSpec("21_systematic.py", "Systematic", "systematic"),
        PageSpec("10_macro.py", "Macro", "macro"),
    ),
    "Risk & Ops": (
        PageSpec("15_sanctions.py", "Sanctions", "sanctions"),
    ),
}


def build() -> st.Page:
    """The run target. app.py owns the masthead above it."""
    return st.navigation(
        {
            section: [
                st.Page(
                    _P + spec.file,
                    title=spec.title,
                    url_path=spec.url_path,
                    default=spec.default,
                )
                for spec in specs
            ]
            for section, specs in PAGES.items()
        },
        position="top",
    )
