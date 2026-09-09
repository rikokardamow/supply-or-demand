# UI Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Kardamow dashboard so it reads as the same publication as
kardamow.substack.com, driven from one token module, and fix the duplicated chart titles.

**Architecture:** A new `core/design.py` owns every chrome colour, family, spacing and
radius value. `.streamlit/config.toml` mirrors those values through Streamlit 1.63's
native theme keys (no CSS hacks), guarded by a drift test because TOML cannot import
Python. `core/theme.py` imports the same module, so chrome and charts cannot diverge. A
component kit replaces the bordered card with hairline sections, and `st.navigation`
replaces the filename-derived sidebar.

**Tech Stack:** Python 3.12, Streamlit 1.63, Plotly 5.x, pytest, uv, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-06-ui-design-system-design.md`

## Global Constraints

- Branch is `design/ui-restyle`, cut from `spec/29-social-sentiment`. Do not rebase onto `main`.
- **A peer Claude session works this same clone.** Confirmed live on 2026-09-06: its commit landed on this branch and one of ours landed on its branch, because both sessions check out branches in one working tree. Before each task, run `ListAgents` and `git log --all --oneline -5`, and confirm the branch is still `design/ui-restyle` before committing. Stage files by name — never `git add -A`, which sweeps a peer's in-progress files into your commit. Never rewrite shared history (`rebase`, `amend`, `branch -f`) while a peer is live; fix mistakes with a follow-up commit.
- Agreed file lanes: this plan owns `apps/dashboard/**`, `core/theme.py`, `core/design.py`, `.streamlit/config.toml`. It does not touch `pipelines/**` or other `core/*` modules.
- `uv` is NOT on the Git Bash PATH on this machine. Run tools as `./.venv/Scripts/python.exe -m <tool>` or from PowerShell. `make dev` fails in Git Bash — this is environmental, not a bug to fix here.
- **Running the app from the worktree needs `PYTHONPATH`, or you will verify the wrong code.** The worktree's `.venv` is a junction to the main clone's, and that venv contains `_editable_impl_energy_dashboard.pth` pointing at `<REPO_ROOT>\Documents\energy-dashboard`. So `import core` resolves to the **main clone**. Confirmed live on 2026-09-06: a screenshot taken to verify Task 5 showed the old doubled titles, because Streamlit was reading `.streamlit/config.toml` from the worktree (cwd-relative, so the new theme appeared) while importing `core` from the main clone. Always start it as:

  ```bash
  PYTHONPATH="<REPO>/Documents/<REPO>.worktrees/ui-restyle" \
    ./.venv/Scripts/streamlit.exe run apps/dashboard/app.py --server.port 8502 --server.headless true
  ```

  `pytest` is unaffected — it puts the rootdir first, which is why the suite tested the right code throughout. The tell-tale is a page that half-updates: new chrome, old behaviour.
- `make check` = ruff, mypy (`core pipelines infra apps`), pytest. Must be green before every commit (golden rule 8).
- Default pytest run excludes browser tests: `addopts = "-ra --strict-markers -m 'not browser'"`. Browser tests run explicitly with `-m browser` and need `playwright install chromium`.
- Series colours (`NAVY #0f2a4a`, `LIGHT_BLUE #5b9bd5`, `RED #c0392b`, `ORANGE #e67e22`, `BAND`, `GRID`) keep their exact current values. They encode data, not brand.
- Chrome tokens, measured from the live Substack: ink `#020617`, paper `#ffffff`, text `#363737`, muted `#757575`, rule `#e6e6e6`, heading family Lora, body/data family Inter.
- Every number, axis tick, table cell and legend label renders in Inter. Lora is for headings only.
- Never pass `use_container_width` to `st.plotly_chart`/`st.dataframe` (deprecated; `width` defaults to `"stretch"`).
- Each page keeps its current URL slug. Slugs come from `_SLUG_RE` in `tests/test_pages_browser.py`.

---

### Task 1: Mockup canvas and approval gate

No code changes. The user chose mockups before implementation; this task produces them.

**Files:**
- Create: a design canvas artifact (published, not committed)

- [ ] **Step 1: Build the canvas**

Use the `design` skill to produce artboards at 1600px wide:
1. Masthead + top nav bar (Overview / Fundamentals / Trading / Risk & Ops)
2. Home page: header, KPI row, lake-status section
3. A chart page (`01_us_padd`): page header, tab strip, two chart sections, a Kardamow take
4. Component states: `section`, `kpi_row`, `empty_state`, `source_note`
5. A map page, showing the Positron basemap treatment (informs the companion spec)

Use the measured tokens from the Global Constraints, not invented ones.

- [ ] **Step 2: Present to the user and WAIT**

The spec states: user approves before any code changes. Do not start Task 2 until the
user has approved the canvas. If they request changes, revise and re-present.

---

### Task 2: `core/design.py` token module

**Files:**
- Create: `core/design.py`
- Create: `tests/test_design_tokens.py`

**Interfaces:**
- Produces: module-level constants consumed by every later task —
  `INK, PAPER, TEXT, MUTED, RULE` (chrome, str hex);
  `NAVY, LIGHT_BLUE, RED, ORANGE, GREY, BAND, GRID, TRANSPARENT` (series, str);
  `STATUS_RED, STATUS_AMBER, STATUS_GREEN` (str);
  `HEADING_FAMILY, BODY_FAMILY, HEADING_STACK, BODY_STACK` (str);
  `HEADING_URL, BODY_URL` (str, Google Fonts css2 URLs);
  `BASE_FONT_PX` (int), `RADIUS` (str).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_tokens.py
"""core/design.py is the single source of truth for chrome tokens (2026-09-06 restyle).

These assertions are deliberately literal: the values were measured off
kardamow.substack.com, and a test that recomputed them from the module would assert
nothing. If a token legitimately changes, the Substack changed -- update both."""

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
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_design_tokens.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'core.design'`

- [ ] **Step 3: Write the module**

```python
# core/design.py
"""Design tokens -- the single definition of chrome colour, type, spacing and radius.

Chrome values are measured from the project's own publication
(https://kardamow.substack.com/) on 2026-09-06, so the dashboard and the Substack read
as one publication. Series colours moved here unchanged from core/theme.py: they encode
data, not brand, and the restyle deliberately leaves them alone.

.streamlit/config.toml cannot import Python, so it repeats several of these values;
tests/test_config_matches_design.py is what stops the two drifting apart."""

from __future__ import annotations

from typing import Final

# -- Chrome (measured from the Substack) -------------------------------------------
INK: Final = "#020617"       # accent, buttons, active nav
PAPER: Final = "#ffffff"     # page ground
TEXT: Final = "#363737"      # primary text
MUTED: Final = "#757575"     # meta lines, captions, source notes
RULE: Final = "#e6e6e6"      # hairline separators

# -- Status (as used by core/freshness.py's report) ---------------------------------
STATUS_GREEN: Final = "#1bc47d"
STATUS_AMBER: Final = "#e67e22"
STATUS_RED: Final = "#c0392b"

# -- Series (unchanged; data, not brand) --------------------------------------------
NAVY: Final = "#0f2a4a"
LIGHT_BLUE: Final = "#5b9bd5"
RED: Final = "#c0392b"
ORANGE: Final = "#e67e22"
GREY: Final = "#95a5a6"
BAND: Final = "rgba(150,150,150,0.25)"
GRID: Final = "#e6e6e6"
TRANSPARENT: Final = "rgba(0,0,0,0)"

# -- Type ----------------------------------------------------------------------------
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

# -- Shape ---------------------------------------------------------------------------
RADIUS: Final = "small"
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_design_tokens.py -v`
Expected: 3 passed

- [ ] **Step 5: Lint, typecheck, commit**

```bash
./.venv/Scripts/python.exe -m ruff check core/design.py tests/test_design_tokens.py
./.venv/Scripts/python.exe -m mypy core
git add core/design.py tests/test_design_tokens.py
git commit -m "feat(design): add core/design.py as the single source of design tokens"
```

---

### Task 3: Theme the app through native Streamlit config

**Files:**
- Modify: `.streamlit/config.toml` (whole `[theme]` block)
- Create: `tests/test_config_matches_design.py`

**Interfaces:**
- Consumes: every constant from Task 2.
- Produces: nothing importable; the running app's chrome.

- [ ] **Step 1: Write the failing drift test**

```python
# tests/test_config_matches_design.py
"""config.toml can't import Python, so its colours are copies. This test is the only
thing preventing chrome and charts from drifting apart again -- which is exactly what
had happened before the 2026-09-06 restyle (navy sidebar vs navy series colour, two
different navies for two different reasons)."""

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
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config_matches_design.py -v`
Expected: FAIL — `KeyError: 'borderColor'` (the current file has no such key)

- [ ] **Step 3: Rewrite the theme block**

Replace the entire contents of `.streamlit/config.toml` with:

```toml
# Values mirror core/design.py -- TOML cannot import Python, so
# tests/test_config_matches_design.py asserts the two agree. Change both together.
[theme]
base = "light"
primaryColor = "#020617"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f7f7f7"
textColor = "#363737"
linkColor = "#020617"
borderColor = "#e6e6e6"
dataframeBorderColor = "#e6e6e6"
showWidgetBorder = false
baseRadius = "small"
baseFontSize = 15
font = "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
headingFont = "Lora:https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&display=swap"
```

The `[theme.sidebar]` block is deleted — Task 7 removes the sidebar itself.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config_matches_design.py -v`
Expected: 3 passed

- [ ] **Step 5: Verify Streamlit accepts every key**

Run: `./.venv/Scripts/streamlit.exe run apps/dashboard/app.py --server.headless true --server.port 8502`

Streamlit logs a warning for an unrecognised or malformed theme key rather than failing.
Read the startup output: there must be **no** theme warning. If `baseRadius = "small"` is
rejected, substitute a CSS length (`"4px"`) and update the test to match. Then open
`http://localhost:8502` and confirm headings render in a serif. Stop the server.

- [ ] **Step 6: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check tests/test_config_matches_design.py
git add .streamlit/config.toml tests/test_config_matches_design.py
git commit -m "feat(design): theme the app from design tokens via native Streamlit config"
```

---

### Task 4: `core/theme.py` reads the token module

**Files:**
- Modify: `core/theme.py:12-20` (the colour constant block) and `register_kardamow_template`
- Modify: `tests/test_design_tokens.py` (add the re-export assertion)

**Interfaces:**
- Consumes: Task 2's constants.
- Produces: `core.theme` keeps re-exporting `NAVY`, `RED`, etc. — `apps/dashboard/pages/01_us_padd.py:19` imports `NAVY, RED` from `core.theme`, and several other pages do the same. Those imports must keep working; this task must not touch page files.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_design_tokens.py`:

```python
def test_theme_reexports_design_colours_not_its_own() -> None:
    """Pages import NAVY/RED from core.theme; that must stay true, but the values must
    now come from core.design so there is one definition, not two."""
    from core import theme

    assert theme.NAVY is design.NAVY
    assert theme.RED is design.RED
    assert theme.LIGHT_BLUE is design.LIGHT_BLUE
    assert theme.ORANGE is design.ORANGE
    assert theme.BAND is design.BAND
    assert theme.GRID is design.GRID
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_design_tokens.py::test_theme_reexports_design_colours_not_its_own -v`
Expected: FAIL — `assert '#0f2a4a' is '#0f2a4a'` fails on identity (two separate literals)

- [ ] **Step 3: Replace the constant block**

In `core/theme.py`, delete the literal assignments at lines 12-20 and import instead:

```python
from core.design import (
    BAND,
    BODY_STACK,
    GREY,
    GRID,
    LIGHT_BLUE,
    NAVY,
    ORANGE,
    RED,
    TEXT,
    TRANSPARENT,
)
```

In `register_kardamow_template`, replace the hard-coded font dict:

```python
    template.layout.font = {"family": BODY_STACK, "color": TEXT}
```

Data must never render in the heading family, so this is the body stack, deliberately.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass. The existing `tests/test_theme_model_charts.py` and
`tests/test_theme_systematic_charts.py` cover the builders and must stay green.

- [ ] **Step 5: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check core/theme.py && ./.venv/Scripts/python.exe -m mypy core
git add core/theme.py tests/test_design_tokens.py
git commit -m "refactor(theme): source chart colours from core/design.py"
```

---

### Task 5: Charts stop painting their own titles

This fixes the defect the screenshots caught: the card header and the plotly title both
render, the plotly one clipped at the card edge and overlapping the legend.

The `title` parameter is **kept and ignored** here, not removed — removing it now would
break all 15 pages in one commit. Task 10 removes it once no caller passes it.

**Files:**
- Modify: `core/theme.py` (36 sites that set `title=`)
- Create: `tests/test_theme_titles.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: figures with `fig.layout.title.text is None`; callers must supply the title to `section()` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme_titles.py
"""No chart builder may paint its own title.

Before the 2026-09-06 restyle every chart section rendered its title twice -- once as
the card header, once as plotly's layout.title -- and the plotly one was clipped at the
card edge and overlapped the top-left legend. The section header owns the title now.

This is a static (AST) check rather than a render check because it must cover all 33
builders without constructing fixture data for each."""

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
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_theme_titles.py -v`
Expected: FAIL, listing roughly 36 sites.

- [ ] **Step 3: Strip the titles**

For each offender, drop the `title=title` keyword, keeping every sibling keyword:

```python
    # before
    fig.update_layout(title=title, yaxis_title=unit)
    # after
    fig.update_layout(yaxis_title=unit)
```

Where `update_layout(title=title)` was the only keyword, delete the whole call.

Signatures keep their `title: str` parameter. Add this note above the first affected
builder so the next reader understands the dead parameter:

```python
# `title` is accepted but no longer painted: the section header owns the title (see
# docs/superpowers/specs/2026-09-06-ui-design-system-design.md). The parameter is
# removed in the page-migration cleanup once no caller passes it.
```

Do NOT touch `xaxis_title` / `yaxis_title` — those are axis labels, not the chart title.
Subplot titles passed to `make_subplots(subplot_titles=...)` also stay.

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_theme_titles.py tests/test_theme_model_charts.py tests/test_theme_systematic_charts.py -q`
Expected: all pass. If a chart test asserted on `fig.layout.title`, update it to assert
the title is absent — that is the intended new behaviour, not a regression.

- [ ] **Step 4b: Stop the annotation sitting on the series**

The Latest / YoY / vs-median annotation currently paints directly over the data. In
`register_kardamow_template` (or the `add_annotation` calls that build it), give it an
opaque ground and a border so it reads as a label rather than an overlay:

```python
    fig.add_annotation(
        # ... existing x/y/text arguments unchanged ...
        bgcolor=PAPER,
        bordercolor=RULE,
        borderwidth=1,
        borderpad=4,
        opacity=0.95,
    )
```

Import `PAPER` and `RULE` from `core.design` alongside the constants added in Task 4.

- [ ] **Step 4c: Move the legend clear of the freed title row**

The legend sat at top-left because the title occupied the row above it; with the title
gone it can take that space. In `register_kardamow_template`, change the legend anchor:

```python
    template.layout.legend = {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.0,          # was 1.02, which pushed it into the title row
        "xanchor": "left",
        "x": 0,
        "font": {"family": BODY_STACK},   # legend labels are data, never the serif
    }
```

- [ ] **Step 4d: Re-run the chart tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_theme_model_charts.py tests/test_theme_systematic_charts.py tests/test_theme_titles.py -q`
Expected: all pass.

- [ ] **Step 5: Verify visually**

Start the app, open `/us_padd`, and confirm each chart shows exactly one title (the card
header) with no clipped text and no legend overlap.

- [ ] **Step 6: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check core/theme.py tests/test_theme_titles.py
git add core/theme.py tests/test_theme_titles.py
git commit -m "fix(theme): stop charts painting titles the card already renders"
```

---

### Task 6: Component kit

**Files:**
- Create: `apps/dashboard/components/section.py`
- Modify: `apps/dashboard/components/card.py` (becomes an alias)
- Create: `tests/test_components_section.py`

**Interfaces:**
- Consumes: Task 2's constants.
- Produces, all imported by pages in Tasks 8-9:
  - `section(title: str) -> Iterator[None]` — context manager
  - `page_header(title: str, as_of: str | None = None, freshness: str | None = None) -> None`
  - `kpi_row(items: Sequence[tuple[str, str, str | None]]) -> None` — (label, value, delta)
  - `empty_state(source: str, cadence: str, last_seen: str | None) -> None`
  - `source_note(text: str) -> None`
  - `card(title: str) -> Iterator[None]` — alias of `section`, removed in Task 10

- [ ] **Step 1: Write the failing test**

```python
# tests/test_components_section.py
"""The component kit is what replaces the bordered card with hairline sections.

AppTest is used rather than a render check because these are Streamlit primitives; the
browser test (-m browser) is what proves they actually paint."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run(body: str) -> AppTest:
    return AppTest.from_string(
        "import sys; sys.path.insert(0, 'apps/dashboard')\n" + body
    ).run(timeout=30)


def test_section_renders_its_title_once() -> None:
    at = _run(
        "from components.section import section\n"
        "with section('Cushing Crude Stocks'):\n"
        "    pass\n"
    )
    assert not at.exception
    assert any("Cushing Crude Stocks" in m.value for m in at.markdown)


def test_card_is_an_alias_so_unmigrated_pages_keep_working() -> None:
    at = _run(
        "from components.card import card\n"
        "with card('Legacy Title'):\n"
        "    pass\n"
    )
    assert not at.exception
    assert any("Legacy Title" in m.value for m in at.markdown)


def test_empty_state_names_the_source_and_its_cadence() -> None:
    at = _run(
        "from components.section import empty_state\n"
        "empty_state('entsog', 'daily', '2026-08-30')\n"
    )
    assert not at.exception
    rendered = " ".join(m.value for m in at.markdown)
    assert "entsog" in rendered
    assert "daily" in rendered
    assert "2026-08-30" in rendered


def test_page_header_renders_title_and_meta() -> None:
    at = _run(
        "from components.section import page_header\n"
        "page_header('US PADD', as_of='SEP 3', freshness='2 of 9 sources stale')\n"
    )
    assert not at.exception
    rendered = " ".join(m.value for m in at.markdown)
    assert "US PADD" in rendered
    assert "SEP 3" in rendered
    assert "2 of 9 sources stale" in rendered
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_components_section.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'components.section'`

- [ ] **Step 3: Write the components**

```python
# apps/dashboard/components/section.py
"""The publication's layout primitives -- hairline rules and whitespace, never boxes.

Replaces the bordered card() the dashboard used before the 2026-09-06 restyle, matching
kardamow.substack.com: a section is a label over a hairline rule, meta lines are
letterspaced grey caps, and nothing is boxed."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import streamlit as st

from core.design import HEADING_STACK, MUTED, RULE, TEXT

_META = (
    f"font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};"
)


@contextmanager
def section(title: str) -> Iterator[None]:
    """A titled content block: heading, hairline rule, then the caller's content."""
    st.markdown(
        f"<div style='font-family:{HEADING_STACK};font-size:1.05rem;font-weight:600;"
        f"color:{TEXT};margin:1.6rem 0 0.15rem'>{title}</div>"
        f"<hr style='border:0;border-top:1px solid {RULE};margin:0 0 0.9rem'>",
        unsafe_allow_html=True,
    )
    yield


def page_header(
    title: str, as_of: str | None = None, freshness: str | None = None
) -> None:
    """Page title in the heading face, with the Substack's caps meta line beneath."""
    st.markdown(
        f"<div style='font-family:{HEADING_STACK};font-size:2.1rem;font-weight:600;"
        f"color:{TEXT};margin:0.2rem 0 0.35rem'>{title}</div>",
        unsafe_allow_html=True,
    )
    meta = " · ".join(part for part in (as_of, freshness) if part)
    if meta:
        st.markdown(f"<div style='{_META}'>{meta}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<hr style='border:0;border-top:1px solid {RULE};margin:0.8rem 0 1.4rem'>",
        unsafe_allow_html=True,
    )


def kpi_row(items: Sequence[tuple[str, str, str | None]]) -> None:
    """A strip of headline numbers: (label, value, delta-or-None) per column."""
    if not items:
        return
    for column, (label, value, delta) in zip(st.columns(len(items)), items, strict=True):
        with column:
            st.metric(label, value, delta)


def empty_state(source: str, cadence: str, last_seen: str | None) -> None:
    """Deliberate NO-DATA rendering. Pages show absence rather than hiding it."""
    seen = last_seen or "never"
    st.markdown(
        f"<div style='{_META}padding:1.6rem 0'>No data · {source} · "
        f"expected {cadence} · last seen {seen}</div>",
        unsafe_allow_html=True,
    )


def source_note(text: str) -> None:
    """Grey caps footnote under a chart -- provenance, units, caveats."""
    st.markdown(f"<div style='{_META}margin-top:-0.4rem'>{text}</div>",
                unsafe_allow_html=True)
```

```python
# apps/dashboard/components/card.py
"""Deprecated alias of components.section.section.

Kept only so pages not yet migrated to the 2026-09-06 restyle keep rendering; it
delegates rather than duplicating, so the two cannot diverge during the migration.
Removed once no page imports it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from components.section import section


@contextmanager
def card(title: str) -> Iterator[None]:
    with section(title):
        yield
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_components_section.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the page smoke tests — nothing may break**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -q`
Expected: all pass. Every page still imports `card`, which now delegates.

- [ ] **Step 6: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check apps/dashboard/components tests/test_components_section.py
./.venv/Scripts/python.exe -m mypy apps
git add apps/dashboard/components/section.py apps/dashboard/components/card.py tests/test_components_section.py
git commit -m "feat(components): hairline section kit, with card() kept as an alias"
```

---

### Task 7: Masthead and top navigation

The riskiest task: both page tests are coupled to `pages/` auto-discovery, which
`st.navigation` replaces.

**Files:**
- Modify: `apps/dashboard/app.py`
- Create: `apps/dashboard/nav.py`
- Modify: `tests/test_pages_smoke.py`
- Verify: `tests/test_pages_browser.py` (should need no change — that is the point of `url_path`)

**Interfaces:**
- Consumes: `page_header` (Task 6), design tokens (Task 2).
- Produces: `nav.PAGES: dict[str, list[st.Page]]` — section name to pages, and `nav.build() -> st.Page`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pages_smoke.py`:

```python
def test_every_page_keeps_its_current_url_slug() -> None:
    """st.navigation replaces filename-derived routing, so each page must declare the
    slug it already had. tests/test_pages_browser.py selects nav links by these slugs,
    and any existing bookmark uses them."""
    import re
    import sys

    sys.path.insert(0, str(REPO_ROOT / "apps" / "dashboard"))
    import nav

    slug_re = re.compile(r"[0-9]*[_ -]*(.*)\.py")
    expected = {
        re.sub(r"[_ ]+", "_", slug_re.fullmatch(name).group(1)).strip("_")
        for name in PAGE_FILES
    }
    actual = {page.url_path for pages in nav.PAGES.values() for page in pages}
    assert actual == expected
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py::test_every_page_keeps_its_current_url_slug -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nav'`

- [ ] **Step 3: Write the navigation module**

```python
# apps/dashboard/nav.py
"""Explicit page registry for st.navigation (2026-09-06 restyle).

Streamlit's pages/ auto-discovery gave lowercase filename labels in a flat sidebar
("app", "us padd") ordered by leading number. st.navigation lets the labels and the
grouping be deliberate -- at the cost of declaring every page here.

url_path is mandatory on every entry: without it Streamlit re-derives routes from the
declared titles, which would silently change every page's URL and break both the
browser test's slug selectors and any existing bookmark."""

from __future__ import annotations

import streamlit as st

_P = "pages/"

PAGES: dict[str, list[st.Page]] = {
    "Overview": [
        st.Page(_P + "015_us_oil_overview.py", title="US Oil Overview",
                url_path="us_oil_overview"),
        st.Page(_P + "09_events.py", title="Events", url_path="events"),
    ],
    "Fundamentals": [
        st.Page(_P + "01_us_padd.py", title="US PADD", url_path="us_padd"),
        st.Page(_P + "02_gas_storage.py", title="Gas Storage", url_path="gas_storage"),
        st.Page(_P + "03_eu_gas_flows.py", title="EU Gas Flows", url_path="eu_gas_flows"),
        st.Page(_P + "04_eu_power.py", title="EU Power", url_path="eu_power"),
        st.Page(_P + "05_us_gas_power.py", title="US Gas & Power",
                url_path="us_gas_power"),
        st.Page(_P + "06_supply.py", title="Supply", url_path="supply"),
        st.Page(_P + "08_weather.py", title="Weather", url_path="weather"),
        st.Page(_P + "19_fundamentals.py", title="Fundamentals",
                url_path="fundamentals"),
    ],
    "Trading": [
        st.Page(_P + "18_curve.py", title="Curve", url_path="curve"),
        st.Page(_P + "20_cracks.py", title="Cracks", url_path="cracks"),
        st.Page(_P + "21_systematic.py", title="Systematic", url_path="systematic"),
        st.Page(_P + "10_macro.py", title="Macro", url_path="macro"),
    ],
    "Risk & Ops": [
        st.Page(_P + "15_sanctions.py", title="Sanctions", url_path="sanctions"),
    ],
}


def build() -> st.Page:
    """Home is declared by app.py, which owns the masthead; this returns the run target."""
    return st.navigation(PAGES, position="top")
```

Cross-check the entries against `ls apps/dashboard/pages/` before running: the set must
be exactly the 15 files, and each `url_path` must equal the slug the browser test derives.

- [ ] **Step 4: Move the home content into a page, and make the entrypoint run navigation**

Under `st.navigation` the entrypoint's job is to render chrome and then run the selected
page. Home content cannot stay inline in `app.py` — it would render on every page. Move
it to a page file and add it to `nav.PAGES["Overview"]` as the default entry:

```python
st.Page(_P + "00_home.py", title="Home", url_path="home", default=True),
```

Create `apps/dashboard/pages/00_home.py` with the current `app.py` body, restyled:

```python
# apps/dashboard/pages/00_home.py
"""Home -- lake status at a glance. Reads the lake, never calls APIs directly."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from components.section import kpi_row, page_header, section
from core.freshness import staleness_report

_STATUS_ORDER = {"red": 0, "amber": 1, "green": 2}
_STATUS_ICON = {"red": "🔴", "amber": "🟡", "green": "🟢"}
# Shorter than the ttl=3600 the analytics pages use. Those cache expensive model fits
# over data that only changes on a pull; this is a *status* panel, and one that keeps
# insisting a source is stale for an hour after the pull that fixed it is worse than
# useless. Five minutes still collapses the many reruns of one browsing session into
# a single query.
_STATUS_TTL_SECONDS = 300


@st.cache_data(ttl=_STATUS_TTL_SECONDS)
def _lake_status() -> pd.DataFrame:
    return staleness_report()


report = _lake_status()
report = report.sort_values(
    by="status", key=lambda col: col.map(_STATUS_ORDER)
).reset_index(drop=True)
counts = report["status"].value_counts()
report["status"] = [f"{_STATUS_ICON[s]} {s}" for s in report["status"]]

page_header(
    "Energy Dashboard",
    as_of=pd.Timestamp.now(tz="UTC").strftime("%d %b %Y").upper(),
    freshness=f"{len(report)} sources tracked",
)
kpi_row(
    [
        ("Sources", str(len(report)), None),
        ("Stale", str(int(counts.get("red", 0))), None),
        ("Ageing", str(int(counts.get("amber", 0))), None),
        ("Current", str(int(counts.get("green", 0))), None),
    ]
)

with section("Lake status"):
    st.caption(
        "Every source across ts_long, flows, events and sanctions, checked against its "
        "own expected pull cadence (see core/freshness.py) — 🟢 within cadence, "
        "🟡 up to 2x cadence, 🔴 beyond that."
    )
    st.dataframe(report, hide_index=True)
```

Then reduce `apps/dashboard/app.py` to masthead plus navigation:

```python
# apps/dashboard/app.py
"""Kardamow Energy Dashboard entrypoint: masthead, then the selected page.

Page content lives in pages/; this file owns only the chrome. st.set_page_config must
be the first Streamlit call, and nav.build().run() must be the last."""

from __future__ import annotations

import streamlit as st
from core.design import HEADING_STACK, RULE, TEXT

st.set_page_config(page_title="Kardamow Energy Dashboard", layout="wide")

st.markdown(
    f"<div style='text-align:center;font-family:{HEADING_STACK};font-size:1.6rem;"
    f"font-weight:600;color:{TEXT};padding:0.4rem 0 0.7rem'>Kardamow</div>"
    f"<hr style='border:0;border-top:1px solid {RULE};margin:0 0 0.4rem'>",
    unsafe_allow_html=True,
)

import nav  # noqa: E402  -- must follow set_page_config

nav.build().run()
```

Adding `00_home.py` means `PAGE_FILES` in the smoke test now has 16 entries and the slug
test expects `home` among them. That is correct and intended, not a test to weaken.

- [ ] **Step 5: Fix the smoke test's page switching**

`test_page_loads_without_raising` calls `at.switch_page(f"pages/{page_file}")`. Run it
first — if `AppTest` still resolves those paths under `st.navigation`, change nothing:

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -q`

If it fails, switch the parametrisation to drive `nav.PAGES` directly, asserting each
page object's script runs without exception, and keep the same one-test-per-page shape so
a single broken page is still identifiable by name.

- [ ] **Step 6: Run the browser test — this is the real gate**

Run: `./.venv/Scripts/python.exe -m pytest -m browser -q`
Expected: all pass with **no change to the file**. If it fails on a nav-link selector,
the `url_path` values are wrong — fix `nav.py`, not the test.

If Chromium is missing: `./.venv/Scripts/python.exe -m playwright install chromium`.

- [ ] **Step 7: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check apps/dashboard tests/test_pages_smoke.py
./.venv/Scripts/python.exe -m mypy apps
git add apps/dashboard/app.py apps/dashboard/nav.py tests/test_pages_smoke.py
git commit -m "feat(nav): grouped top navigation and a masthead home page"
```

---

### Task 8: Migrate the reference page (`01_us_padd`)

Establishes the pattern the remaining 14 follow. Chosen because it has charts, tabs, a
map and a Kardamow take — every construct in one file.

**Files:**
- Modify: `apps/dashboard/pages/01_us_padd.py`

**Interfaces:**
- Consumes: `section`, `page_header`, `source_note`, `empty_state` (Task 6).
- Produces: the migration pattern for Task 9.

- [ ] **Step 1: Confirm the page renders before touching it**

Run: `./.venv/Scripts/python.exe -m pytest "tests/test_pages_smoke.py::test_page_loads_without_raising[01_us_padd.py]" -v`

- [ ] **Step 2: Apply the migration**

Four mechanical changes:

1. `from components.card import card` becomes `from components.section import page_header, section, source_note`.
2. The bare `st.title("US PADD — Crude & Product Movements")` becomes:

   ```python
   page_header(
       "US PADD — Crude & Product Movements",
       as_of=f"NEXT WPSR {next_release('eia_wpsr').strftime('%d %b %H:%M ET').upper()}",
   )
   ```

   `core.calendars.next_release` is already imported at line 21 of this page. Check its
   actual signature and the key it expects before writing this — if the page already
   computes and renders a release string somewhere below, reuse that expression verbatim
   rather than constructing a second one.
3. Every `with card(<short title>):` becomes `with section(<full title>):`, where the
   full title is the string the chart used to paint — e.g. `card("Cushing Crude Stocks")`
   wrapping `seasonal_range_chart(..., title="Cushing Crude Stocks — Seasonal Range")`
   becomes `section("Cushing Crude Stocks — Seasonal Range")`. The fuller string is the
   better one and must not be lost; that is the whole point of Task 5.
4. Where the page renders a bare "no data" message, call `empty_state(source, cadence, last_seen)`.

Leave the `title=` argument in the chart calls — Task 10 removes it everywhere at once.

- [ ] **Step 3: Verify no page raises**

Run: `./.venv/Scripts/python.exe -m pytest "tests/test_pages_smoke.py::test_page_loads_without_raising[01_us_padd.py]" -v`

- [ ] **Step 4: Look at it**

Start the app, open `/us_padd`. Confirm: one title per chart, no clipping, no legend
overlap, hairline rules instead of boxes, serif headings, sans-serif numbers and ticks.

- [ ] **Step 5: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check apps/dashboard/pages/01_us_padd.py
git add apps/dashboard/pages/01_us_padd.py
git commit -m "refactor(padd): migrate the reference page to the section kit"
```

---

### Task 9: Migrate the remaining 14 pages

One commit per page. A page is one unit of review, and a bad migration must be revertable
without taking the others with it.

**Files:** each of `apps/dashboard/pages/*.py` except `01_us_padd.py`.

- [ ] **Step 1: For each page, in this order**

`015_us_oil_overview`, `02_gas_storage`, `03_eu_gas_flows`, `04_eu_power`,
`05_us_gas_power`, `06_supply`, `08_weather`, `09_events`, `10_macro`, `15_sanctions`,
`18_curve`, `19_fundamentals`, `20_cracks`, `21_systematic`:

1. Replace `from components.card import card` with
   `from components.section import page_header, section, source_note`.
2. Replace `st.title("<Page Title>")` with `page_header("<Page Title>")`, adding
   `as_of=` only where the page already computes a release or as-of date — do not
   invent one.
3. Replace every `with card(<short title>):` with `with section(<full title>):`, where
   the full title is the string that page passes as the chart's `title=` argument. Where
   the two differ (card `"Cushing Crude Stocks"` vs chart
   `"Cushing Crude Stocks — Seasonal Range"`), keep the fuller one — recovering it is the
   point of Task 5, and dropping it loses information the chart used to show.
4. Replace any bare "no data" text with `empty_state(source, cadence, last_seen)`,
   importing it alongside the others.
5. Run `./.venv/Scripts/python.exe -m pytest "tests/test_pages_smoke.py::test_page_loads_without_raising[<file>]" -v`
6. Open the page in the running app and check it.
7. `git commit -m "refactor(<page>): migrate to the section kit"`

`08_weather` holds the cartopy anomaly maps. Do not restyle those figures — they are
matplotlib, out of scope, and explicitly excluded by the companion spec.

**Sections handed over by the peer session (commit `fde6135`, Spec 30).** These landed
in the old `card(...)` idiom by agreement, before this migration reached them. They are
not on this branch yet — merge their branch before starting Task 9. The peer chose the
better of each competing title; use these exact strings for `section()`:

| File | Section title to use |
|---|---|
| `20_cracks.py` | `"Refiner acquisition cost vs WTI and Brent spot"` — settled by their commit `5a90098` |
| `20_cracks.py` | `"Landed cost of imported crude by API gravity band"` — "imported crude" is load-bearing, do not shorten |
| `20_cracks.py` | `"Retail-to-wholesale margin"` — the card string wins; the chart's "US retail gasoline vs NY Harbor wholesale, with the margin" is a mouthful as a heading. Changed by their commit `b9ccb0d`, which rebuilt this section: it now shows 2 series (retail vs wholesale, with the margin annotated) instead of 12 pump-price levels |
| `05_us_gas_power.py` | `"State cost of natural gas delivered to generators vs Henry Hub"` |

New functions to migrate alongside the existing ones: `_acquisition_cost_section`,
`_landed_cost_section`, `_retail_margin_section` (cracks); `_generator_fuel_series_id`,
`_delivered_fuel_cost_section` (gas power).

**Do not drop either reference line from the acquisition-cost chart in the name of
visual cleanliness.** Domestic refiner acquisition cost tracks WTI; imported tracks
Brent. With only one benchmark drawn, the imported series reads as persistently
mispriced when it is simply following the other one. Both references are what make the
composite/domestic/imported split legible. (From the peer session, which built it.)

**Findings from the peer's Spec 30 review, split by who owns them.** Their review found
four things in these two files. The split follows the real seam: they own *what the
chart shows* (they wrote the spec and know the series), this plan owns *how it looks*.

Theirs to land before Task 10, in the old `card()` idiom:

- `05_us_gas_power.py:268` — `GENERATOR_FUEL[0]` picks the cost series by list index. Reordering that list silently plots consumption in thousand Mcf against a `$/MMBtu` axis beside Henry Hub; nothing raises. Fixed by importing their new `GENERATOR_FUEL_COST_KEY`. Ships atomically with the constant, so there is never a window where the constant exists unused.
- `05_us_gas_power.py:259-271` — the page re-derives the minted series ID, hardcoding `_GENERATOR_FUEL_FREQ_CODE = "M"`, duplicating `client.py`. If the route's frequency changes the page asks for `…​.M`, the client wrote `…​.Q`, and the chart says "no data" over a full lake. Fixed by calling their exported `generator_fuel_series_id()`.
- Two spec gaps: the delivered-cost chart never computes or annotates the spread (spec line 124), and `_retail_margin_section` shows 12 pump-price levels with no wholesale leg and therefore no margin, despite its name and its own caption (spec lines 126-127). Composition, not styling — they hold the spec.

Mine, in Task 9:

- After they land the above, migrate their annotation to the house treatment: direct annotation near the last point, using the opaque-ground/hairline-border styling from Task 5, not an ad-hoc box.
- `20_cracks.py:128` — `_PRICE_PALETTE` cycles four colours over 12 retail and 8 RAC series, so `R0000____3` (the US composite headline) renders identically to `R0040____3` (PADD4). **The fix is not more colours.** Cycling a categorical palette is the failure; a 9th series never gets a generated hue. Emphasise the composite (full-weight navy, direct-labelled) and drop the rest to a muted common grey, or facet into small multiples. Decide when the section is migrated and the real chart is in front of you.
was expanded from single-line to parenthesised multi-line to add `GREY, LIGHT_BLUE,
NAVY`. Nothing was removed. This plan rewrites that same import line, so resolve by
keeping their colour names and switching the `card` import to `components.section`.

- [ ] **Step 2: Full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q` then `./.venv/Scripts/python.exe -m pytest -m browser -q`
Expected: both green.

- [ ] **Step 3: Confirm nothing still imports the alias**

Run: `grep -rn "components.card\|from components import card" apps/`
Expected: no matches.

---

### Task 10: Remove the dead parameter, update the rules, record the result

**Files:**
- Modify: `core/theme.py` (signatures), every page passing `title=` to a builder
- Delete: `apps/dashboard/components/card.py`
- Modify: `CLAUDE.md` (rule 5 and "Dashboard layout — institutional look")
- Modify: `tests/test_components_section.py` (drop the alias test)

- [ ] **Step 1: Remove `title` from the builders that no longer use it**

For each builder whose `title` parameter is now unreferenced, delete the parameter and
every `title=` argument at its call sites. Builders that still use `title` for subplot
annotations keep it.

- [ ] **Step 2: Let the type checker find the stragglers**

Run: `./.venv/Scripts/python.exe -m mypy core pipelines infra apps`
Expected: clean. Any "unexpected keyword argument 'title'" is a call site to fix.

- [ ] **Step 3: Delete the alias**

```bash
rm apps/dashboard/components/card.py
```
Remove `test_card_is_an_alias_so_unmigrated_pages_keep_working` from
`tests/test_components_section.py`.

- [ ] **Step 4: Rewrite the CLAUDE.md rules**

Rule 5 currently says charts use `core.theme`; extend it to name `core/design.py` as the
token source. Replace the "Dashboard layout — institutional look" section: the navy
sidebar and the bordered `card()` are gone; describe the masthead, grouped top
navigation, hairline sections, Lora headings over Inter data, and the rule that no chart
paints its own title. Leave the `use_container_width` guidance and the `Scattergeo`
prohibition intact. The map rule stays as-is until the companion spec lands.

- [ ] **Step 5: Full green gate**

Run: `./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy core pipelines infra apps && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m pytest -m browser -q`
Expected: all green.

- [ ] **Step 6: Re-shoot all 16 pages**

Re-run the screenshot script used before this plan against the running app, writing to a
fresh directory, and compare page by page against the "before" set. Every page must be
legible, with no clipped text, no boxes, and no serif numerals.

- [ ] **Step 7: Commit and update the changelog**

```bash
# Name every file. A peer session works this same clone, and `git add -A` sweeps their
# in-progress files into your commit -- this has already happened once on this repo.
git add core/theme.py CLAUDE.md CHANGELOG.md tests/test_components_section.py
git add apps/dashboard/pages          # the call sites that dropped title=
git rm apps/dashboard/components/card.py
git commit -m "refactor(theme): drop the unused title parameter; update CLAUDE.md for the restyle"
```

Add a `CHANGELOG.md` entry in the established narrative style, recording what shipped and
the duplicate-title defect that prompted the chart change.

---

## After this plan

The companion spec `2026-09-06-leaflet-maps-design.md` gets its own plan, written once
this one lands — it depends on `core/design.py` existing so `basemap.py` can read the
same tokens.
