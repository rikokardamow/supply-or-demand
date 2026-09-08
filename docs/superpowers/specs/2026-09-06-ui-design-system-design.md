# Design — UI design system restyle (Substack-aligned)

**Date:** 2026-09-06
**Status:** approved design, not yet planned
**Branch:** `design/ui-restyle` (cut from `spec/29-social-sentiment`, not `main` — see Constraints)
**Companion spec:** `2026-09-06-leaflet-maps-design.md` (ships after this one)

## Why now

The recorded project decision was to defer the UI rework until the spec pack was
finished, so pages would not be restyled twice. On 2026-09-06 the user overrode that
deliberately, and additionally supplied a visual reference that did not exist when the
deferral was made: the publication this dashboard belongs to,
<https://kardamow.substack.com/>. The dashboard should read as the same publication as
the Substack.

The override is the reason this spec exists. Specs 22–28 are still unbuilt, so their
pages will be authored against the component kit defined here rather than retrofitted.

## Goal

The dashboard reads as the same publication as the Substack, while remaining a dense
data tool. Concretely:

- One place defines colour, type, spacing and radius; chrome and charts cannot drift.
- Page chrome matches the Substack: centred wordmark masthead, top tab navigation,
  hairline rules and whitespace instead of bordered boxes, letterspaced caps meta lines.
- Serif (Lora) for headings; sans (Inter) for every number, axis tick, table cell and
  chart label.
- The duplicate and clipped chart titles visible today are gone.

## Non-goals

- No new visual identity invented here. The identity is the Substack's, measured, not designed.
- No change to what any page computes, or to any lake read.
- No page-template framework (approach C, rejected below).
- Maps are out of scope — companion spec.
- Not a Streamlit replacement. The app stays Streamlit.

## The reference, measured

Read off the live site with Playwright on 2026-09-06, not eyeballed:

| Token | Value |
|---|---|
| Heading and body family | `Lora, sans-serif` (`--font-family-pub-headings`, `--font-family-pub-body`) |
| Accent / button ground | `#020617` (`--color_theme_accent`, `--background_pop`) |
| Page ground | `#ffffff` (`--web_bg_color`) |
| Primary text | `#363737` (`--color-fg-primary-themed`) |
| Secondary text | `#757575` |
| Hairline rule | `#e6e6e6` (`--color-utility-detail-themed`) |
| Article body size | 19px, generous leading |

Structure: thin white masthead, centred `Kardamow` wordmark, horizontal tab bar beneath
with the active tab underlined, content separated by hairline rules and whitespace with
**no bordered boxes anywhere**, and small meta set as letterspaced grey caps
(`SEP 3 • RIKO KARDAMOW`).

## Current state, measured

All 16 pages were screenshotted against the real lake before this spec was written.

- Navigation is Streamlit's filename-derived sidebar on a navy `#0f2a4a` ground:
  lowercase labels (`us padd`, `gas storage`), the home page labelled `app`, no grouping.
- Every section is a bordered `st.container` via `components/card.py` (17 lines).
- **Defect:** each chart card prints its title twice — once as the card header, once as
  the plotly `layout.title` — and the plotly title is clipped at the card edge *and*
  overlaps the top-left legend. The Latest / YoY / vs-median annotation sits on top of
  the series. Reproduced on `01_us_padd` (both columns) and repeating across pages.
  Root cause: `card()` and `core/theme.py` each assume they own the title.
- The home page is one table in one box with the rest of the viewport empty; no as-of
  date, no freshness summary, no KPI row.

## Approach

Chosen: **design tokens plus a component kit**, with pages adopting the kit incrementally.

Rejected:

- *CSS-only skin.* Cannot deliver grouped navigation, empty states or the chart fixes,
  and Streamlit-internal class selectors break on upgrade.
- *Page-template framework* (`render_page(spec)`). Maximum consistency, but rewrites all
  15 pages up front, fights how Streamlit pages are written, and collides with the
  `/new-page` workflow while specs 22–28 still have pages to add.

## Architecture

### 1. `core/design.py` — token source of truth

New flat module beside the other `core/*.py` modules. Owns:

- **Chrome palette:** `INK = "#020617"`, `PAPER = "#ffffff"`, `TEXT = "#363737"`,
  `MUTED = "#757575"`, `RULE = "#e6e6e6"`.
- **Status palette:** the existing red / amber / green used by `core/freshness.py`.
- **Series palette:** `NAVY`, `LIGHT_BLUE`, `RED`, `ORANGE`, `BAND`, `GRID` — moved here
  unchanged from `core/theme.py`.
- **Type:** heading family Lora, body and data family Inter, the size and weight scale.
- **Spacing and radius** scales.

`core/theme.py` imports these instead of defining `NAVY = "#0f2a4a"` at module top.

**Series colours keep their current values.** They encode data, not brand: navy primary,
light blue secondary, red accent, orange seasonal median. Only chrome adopts the
Substack ink. Changing series colours would invalidate every chart convention in
`CLAUDE.md` and every Kardamow take that refers to them.

### 2. `.streamlit/config.toml` — native theming

Streamlit 1.63, verified against the installed venv, exposes all of these natively, so
no CSS hacks against internal class names are needed:

`theme.font`, `theme.headingFont`, `theme.fontFaces`, `theme.headingFontSizes`,
`theme.headingFontWeights`, `theme.baseFontSize`, `theme.baseRadius`,
`theme.borderColor`, `theme.showWidgetBorder`, `theme.linkColor`,
`theme.dataframeBorderColor`, `theme.dataframeHeaderBackgroundColor`,
`theme.metricValueFontSize`.

Mapping: `font` = Inter (unchanged), `headingFont` = Lora, `primaryColor` = `INK`,
`textColor` = `TEXT`, `borderColor` = `RULE`, `showWidgetBorder = false`, and a small
`baseRadius`. Lora is loaded with the same `"Family:https://fonts.googleapis.com/..."`
shorthand the file already uses for Inter, so there is one loading mechanism, not two.

The sidebar theme block is removed along with the sidebar itself (§3).

**Drift guard.** `config.toml` cannot import Python, so the hexes necessarily exist in
two places. A test parses `.streamlit/config.toml` and asserts every colour matches
`core/design.py`. This is the mechanism that keeps chrome and charts aligned after this
spec ships; without it the two halves drift the way they already have.

### 3. Chrome — `apps/dashboard/app.py`

Adopt `st.navigation(pages, position="top")`, native in 1.63, with named sections:
Overview / Fundamentals / Trading / Risk & Ops. Above it, a centred `Kardamow` wordmark
in Lora over a hairline rule, matching the Substack masthead.

Two load-bearing consequences:

- `st.navigation` requires an explicit `st.Page` per file, so `pages/` auto-discovery
  ends and page order and labels become explicit — which is what fixes `app` and
  `us padd` as navigation labels.
- **Each page must pass `url_path` set to its current slug.** `tests/test_pages_browser.py`
  selects nav links by the slug derived from `_SLUG_RE`, and bookmarks use the same path.
  Omitting `url_path` silently renames every route and breaks both.

### 4. Component kit — `apps/dashboard/components/`

| Component | Purpose |
|---|---|
| `page_header(title, as_of, freshness)` | Lora title plus letterspaced grey caps meta line |
| `section(title)` | Replaces the bordered card: hairline rule and label; owns the title |
| `kpi_row(items)` | Metric strip for the top of a page |
| `empty_state(source, cadence, last_seen)` | Real NO-DATA treatment, replacing bare text |
| `source_note(text)` | Grey caps footnote under a chart |

`card()` is kept as a thin alias of `section()` with its current signature, so the 15
existing pages keep rendering while they migrate one at a time. It is removed in the
final cleanup commit, once no page calls it.

### 5. Chart layer — `core/theme.py`

- **Chart builders stop setting `layout.title`.** The section header owns the title.
  This single change removes the duplicate title, the clipping and the legend collision.

  There must be exactly one source for a title, so where the `title` parameter fed only
  `layout.title` it is **removed from the signature**, and the page passes the composed
  string to `section()` instead. Today the two disagree — the card says
  `Cushing Crude Stocks` while the figure says `Cushing Crude Stocks — Seasonal Range` —
  and the fuller string is the better one, so it moves to the section header rather than
  being dropped. Where `title` feeds subplot annotations rather than `layout.title`, it
  stays. This ripples to every call site; that is a mechanical, test-guarded refactor and
  is preferred over leaving a parameter that silently does nothing.
- Legend placement moves clear of the freed title row.
- The Latest / YoY / vs-median annotation gets a solid background and an offset so it
  stops sitting on the series.
- Axis tick and legend fonts are pinned to Inter explicitly, so a serif heading font can
  never leak into numerals.
- All colour constants come from `core/design.py`.

Mechanical across the 33 builders; the smoke and browser tests are the guard.

### 6. `CLAUDE.md`

Rule 5 and the "Dashboard layout — institutional look" section currently mandate the
bordered `card()` and describe the navy sidebar. They are rewritten in the final commit
of this spec. Leaving them would make the rules file contradict the code.

## Error handling and edge cases

- **Webfont fails to load** (offline, or Google Fonts blocked): both families declare
  real fallback stacks — Lora to Georgia to serif, Inter to system sans. Layout must not
  depend on metrics unique to either.
- **Page with no data:** `empty_state` renders source, expected cadence and last-seen,
  reusing `core/freshness.py`. Pages deliberately render NO-DATA rather than hiding, and
  that stays true.
- **Long page titles** wrap in the masthead rather than truncating.
- **Migration window:** pages using `card()` and pages using `section()` coexist and must
  both look acceptable. `card()` delegates to `section()`, so they cannot diverge.

## Testing

- `tests/test_pages_smoke.py` and `pytest -m browser` are the gate, unchanged in intent.
  The browser test's slug selectors must keep passing — that is the `url_path` check.
- New: token-drift test (`config.toml` against `core/design.py`).
- New: a test asserting no `core/theme.py` builder sets `layout.title`, so the duplicate
  title cannot regress.
- Before and after: all 16 pages re-screenshotted with the same script and compared.
- `make check` (ruff, mypy, pytest) green before each commit, per golden rule 8.

## Rollout order

1. Mockup canvas — masthead, home, a chart page, a map page, component states. **User
   approves before any code changes.**
2. `core/design.py`, `config.toml`, drift test.
3. Chrome: masthead, `st.navigation` with `url_path`, section grouping.
4. Component kit, with `card()` aliased.
5. One reference page end to end (`01_us_padd` — it has charts, tabs and a map).
6. Remaining 14 pages.
7. Chart layer: title ownership, legend, annotations.
8. `CLAUDE.md` rewrite, `card()` removal, before and after screenshots.

## Constraints

- The branch is cut from `spec/29-social-sentiment`, not `main`: that branch is unmerged
  and carries `21_systematic.py` and 199 lines of new `core/theme.py` builders.
  Branching from `main` would restyle a codebase missing a page and several chart functions.
- The app runs from the project venv (`.venv/Scripts/streamlit.exe`); `uv` is not on the
  Git Bash PATH on this machine, so `make dev` fails there. Unrelated to this spec, but
  it is how the screenshots and browser tests get run.

## Definition of done

- [ ] `core/design.py` is the only definition of chrome colour, type, spacing and radius.
- [ ] Drift test passes; `config.toml` and `core/design.py` agree.
- [ ] Top navigation with named sections; every page keeps its current URL slug.
- [ ] No page renders a bordered box; sections are hairline rules.
- [ ] No chart paints its own title; no clipped or duplicated titles on any of the 16 pages.
- [ ] Every number, tick and table cell renders in Inter; every heading in Lora.
- [ ] `make check` green; `pytest -m browser` green.
- [ ] `CLAUDE.md` describes the shipped design, not the old one.
- [ ] Before and after screenshots of all 16 pages recorded.
