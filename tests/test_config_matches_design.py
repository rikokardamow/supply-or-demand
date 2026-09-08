"""config.toml can't import Python, so its colours are copies.

This test is the only thing preventing chrome and charts from drifting apart again --
which is exactly what had happened before the 2026-09-06 restyle (a navy sidebar and a
navy series colour, two different navies chosen for two different reasons).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from core import design

CONFIG = Path(__file__).parent.parent / ".streamlit" / "config.toml"


def _theme() -> dict[str, object]:
    with CONFIG.open("rb") as handle:
        return dict(tomllib.load(handle)["theme"])


def test_config_colours_come_from_design_module() -> None:
    theme = _theme()
    assert theme["primaryColor"] == design.INK
    assert theme["backgroundColor"] == design.PAPER
    assert theme["textColor"] == design.TEXT
    assert theme["borderColor"] == design.RULE
    assert theme["linkColor"] == design.INK


def test_config_fonts_come_from_design_module() -> None:
    theme = _theme()
    assert theme["font"] == f"{design.BODY_FAMILY}:{design.BODY_URL}"
    assert theme["headingFont"] == f"{design.HEADING_FAMILY}:{design.HEADING_URL}"


def test_widget_borders_are_off() -> None:
    """The Substack separates content with hairline rules and whitespace, never boxes."""
    assert _theme()["showWidgetBorder"] is False
