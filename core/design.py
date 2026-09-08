"""Design tokens -- the single definition of chrome colour, type, spacing and radius.

Chrome values are measured from the project's own publication
(https://kardamow.substack.com/) on 2026-09-06, so the dashboard and the Substack read
as one publication. Series colours moved here unchanged from core/theme.py: they encode
data, not brand, and the restyle deliberately leaves them alone.

.streamlit/config.toml cannot import Python, so it repeats several of these values;
tests/test_config_matches_design.py is what stops the two drifting apart.
"""

from __future__ import annotations

from typing import Final

# -- Chrome (measured from the Substack) --------------------------------------------
INK: Final = "#020617"  # accent, buttons, active nav
PAPER: Final = "#ffffff"  # page ground
TEXT: Final = "#363737"  # primary text
MUTED: Final = "#757575"  # meta lines, captions, source notes
RULE: Final = "#e6e6e6"  # hairline separators

# -- Status (the red/amber/green of core/freshness.py's report) ----------------------
STATUS_GREEN: Final = "#1bc47d"
STATUS_AMBER: Final = "#e67e22"
STATUS_RED: Final = "#c0392b"

# -- Series (unchanged; data, not brand) ---------------------------------------------
NAVY: Final = "#0f2a4a"
LIGHT_BLUE: Final = "#5b9bd5"
RED: Final = "#c0392b"
ORANGE: Final = "#e67e22"
GREY: Final = "#95a5a6"
BAND: Final = "rgba(150,150,150,0.25)"
GRID: Final = "#e6e6e6"
TRANSPARENT: Final = "rgba(0,0,0,0)"

# -- Type -----------------------------------------------------------------------------
HEADING_FAMILY: Final = "Lora"
BODY_FAMILY: Final = "Inter"
# Real fallbacks: the app must stay legible with Google Fonts blocked or offline.
HEADING_STACK: Final = "Lora, Georgia, 'Times New Roman', serif"
BODY_STACK: Final = "Inter, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
HEADING_URL: Final = (
    "https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&display=swap"
)
BODY_URL: Final = (
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
)
BASE_FONT_PX: Final = 15

# -- Shape ----------------------------------------------------------------------------
RADIUS: Final = "small"
