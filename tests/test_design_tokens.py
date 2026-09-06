"""core/design.py is the single source of truth for chrome tokens (2026-09-06 restyle).

These assertions are deliberately literal: the values were measured off
kardamow.substack.com, and a test that recomputed them from the module would assert
nothing. If a token legitimately changes, the Substack changed -- update both.
"""

from __future__ import annotations

from core import design


def test_chrome_tokens_match_the_substack() -> None:
    assert design.INK == "#020617"
    assert design.PAPER == "#ffffff"
    assert design.TEXT == "#363737"
    assert design.MUTED == "#757575"
    assert design.RULE == "#e6e6e6"


def test_series_colours_are_unchanged_from_theme() -> None:
    """Series colours encode data, not brand -- the restyle must not move them."""
    assert design.NAVY == "#0f2a4a"
    assert design.LIGHT_BLUE == "#5b9bd5"
    assert design.RED == "#c0392b"
    assert design.ORANGE == "#e67e22"
    assert design.BAND == "rgba(150,150,150,0.25)"
    assert design.GRID == "#e6e6e6"


def test_data_never_renders_in_the_heading_family() -> None:
    assert design.HEADING_FAMILY == "Lora"
    assert design.BODY_FAMILY == "Inter"
    assert design.HEADING_STACK.startswith("Lora,")
    assert "serif" in design.HEADING_STACK
    assert design.BODY_STACK.startswith("Inter,")
