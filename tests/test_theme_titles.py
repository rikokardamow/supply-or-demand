"""No chart builder, page, or component may paint its own title.

Before the 2026-09-06 restyle every chart section rendered its title twice -- once as
the card header, once as plotly's layout.title -- and the plotly one was clipped at the
card edge and overlapped the top-left legend. The section header owns the title now.

This is a static (AST) check rather than a render check because it must cover every
builder without constructing fixture data for each. It scans two shapes of offender:
the keyword form (`update_layout(title=...)`/`go.Layout(title=...)`) and the dict form
(`go.Figure(layout={"title": ...})`) -- both existed for real in this branch (the dict
form in `signal_board_table`/`fractionation_heatmap`, self-painted titles outside
`core/theme.py` in `apps/dashboard/pages/01_us_padd.py` and several
`apps/dashboard/components/*_map.py` files) before being fixed, so it scans all of
`core/theme.py` plus every page and component under `apps/dashboard/`, not just the
builders module. `gauge_chart`'s `go.Indicator(title=...)` is a deliberate, sanctioned
exception -- it labels the indicator trace itself, real in-plot content -- and is
correctly untouched by either check since it is neither `update_layout`/`Layout` nor a
`layout={...}` dict passed to `go.Figure(...)`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
THEME = REPO_ROOT / "core" / "theme.py"
DASHBOARD_DIR = REPO_ROOT / "apps" / "dashboard"


def _scan_paths() -> list[Path]:
    """core/theme.py plus every page and component module under apps/dashboard/."""
    return [THEME, *sorted(DASHBOARD_DIR.rglob("*.py"))]


def _title_offenders(path: Path) -> list[str]:
    """Every `title=` keyword to update_layout(...)/Layout(...), and every `"title"`
    key inside a `layout={...}` dict literal passed to go.Figure(...), in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(REPO_ROOT)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in {"update_layout", "Layout"}:
            for kw in node.keywords:
                if kw.arg == "title":
                    offenders.append(f"{rel}: {name}(title=...) at line {node.lineno}")
        elif name == "Figure":
            for kw in node.keywords:
                if kw.arg != "layout" or not isinstance(kw.value, ast.Dict):
                    continue
                for key in kw.value.keys:
                    if isinstance(key, ast.Constant) and key.value == "title":
                        offenders.append(
                            f"{rel}: Figure(layout={{'title': ...}}) at line {node.lineno}"
                        )
    return offenders


def test_no_builder_paints_its_own_title() -> None:
    offenders = [offender for path in _scan_paths() for offender in _title_offenders(path)]
    assert offenders == [], (
        "these set layout.title, which duplicates the section header: " + ", ".join(offenders)
    )
