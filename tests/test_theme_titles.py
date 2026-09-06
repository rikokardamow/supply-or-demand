"""No chart builder may paint its own title.

Before the 2026-09-06 restyle every chart section rendered its title twice -- once as
the card header, once as plotly's layout.title -- and the plotly one was clipped at the
card edge and overlapped the top-left legend. The section header owns the title now.

This is a static (AST) check rather than a render check because it must cover all 33
builders without constructing fixture data for each.
"""

from __future__ import annotations

import ast
from pathlib import Path

THEME = Path(__file__).parent.parent / "core" / "theme.py"


def _layout_title_keywords() -> list[str]:
    """Every `title=` keyword passed to update_layout(...) or go.Layout(...)."""
    tree = ast.parse(THEME.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in {"update_layout", "Layout"}:
            continue
        for kw in node.keywords:
            if kw.arg == "title":
                offenders.append(f"{name} at line {node.lineno}")
    return offenders


def test_no_builder_paints_its_own_title() -> None:
    offenders = _layout_title_keywords()
    assert offenders == [], (
        "these set layout.title, which duplicates the section header: "
        + ", ".join(offenders)
    )
