# Design — Terminal UI for `web/` (Bloomberg-style)

**Date:** 2026-09-09
**Status:** REINSTATED 2026-09-09 and in build on `design/terminal-ui`. Briefly
superseded the same day when the user chose to keep the light product UI, then reinstated
— "blog page as magazine, data as Terminal", confirmed directly. The direction has moved
four times and data.kardamow.com is live, so the work is branch-only and **the merge is
the user's decision**. Plan: `docs/superpowers/plans/2026-09-09-terminal-ui.md`.
**Surface:** `web/` (Next.js, data.kardamow.com) only
**Does not touch:** `apps/dashboard/` (Streamlit), `core/design.py`

## Why

The user asked for "similar design as Bloomberg terminal". The current `web/` surface is
a light product UI — `#f4f6f8` ground, white cards with radius and soft shadows, Inter
throughout, a centred 1240px measure. Its own `tokens.css` header describes it as "a
product interface"; a terminal is close to the inverse of it.

Choosing `web/` over the Streamlit app is deliberate and was confirmed with the user: the
last five commits are all `web/src/**`, `TickerRail`/`Masthead`/`StatStrip` already exist
there, and a terminal aesthetic reached through Streamlit would mean fighting its chrome
with injected CSS. The Streamlit app keeps the Substack identity it was restyled to on
2026-09-08 (see `2026-09-06-ui-design-system-design.md`).

## Goal

`web/` reads unmistakably as a terminal — black ground, monospace, amber accent, zero
radius, 1px rules, high information density, edge-to-edge — while staying readable for an
hour at a stretch. All 14 routes inherit it from one token file plus a small primitive
layer; no route is restyled individually.

## Decisions taken (with the user, 2026-09-09)

1. **Surface:** `web/` only.
2. **Fidelity:** terminal-authentic, modern legibility. Not a CRT pastiche: body text is
   near-white, not amber, because amber-on-black for long reads is the part of the real
   terminal worth leaving behind.
3. **Scope:** skin + density rework. No command line, no function-key navigation.
4. **Series colours:** roles preserved, values re-derived for a black ground.
5. **Amber:** *as ink* — amber type on dark header strips. Solid amber bars are rationed
   to the active nav item and stale badges, so amber keeps meaning something across a
   page of eight panels and a stale warning still has somewhere louder to go.
6. **Layout:** full-bleed, edge to edge. `--measure` comes out of the page wrappers.
7. **Density:** 11px base, ~17px table rows, hairlines within tables, solid borders
   between panels.

## Non-goals

- A Bloomberg-style command line (mnemonic + GO) or function-key shortcuts. This was
  offered as a scope option and declined; it would need its own spec.
- Any change to `apps/dashboard/` or `core/design.py`.
- A light/dark toggle. A terminal with a light mode is not the thing that was asked for,
  and it would double what every future page has to satisfy.
- New pages, new data, or changes to what any route queries.

## Architecture

### `web/src/theme/tokens.css` — rewritten

Chrome tokens:

| Token | Value | Role |
|---|---|---|
| `--bg` | `#000000` | page ground |
| `--surface` | `#0a0b0d` | panel/bar ground |
| `--surface-2` | `#131519` | panel header strip, row hover |
| `--border` | `#2a2f37` | panel and table-header borders |
| `--hairline` | `#16191f` | between table rows |
| `--text` | `#e6e8eb` | body and figures |
| `--muted` | `#9aa2ad` | labels, secondary |
| `--faint` | `#7d8590` | cadence lines, source notes |
| `--accent` | `#ff9e1b` | amber: panel labels, active nav, wordmark |
| `--up` | `#16c784` | positive change |
| `--down` | `#ee4a56` | negative change |

Type: one mono stack (`"JetBrains Mono", "IBM Plex Mono", ui-monospace,
SFMono-Regular, Menlo, Consolas, monospace`) for every label, figure, heading and table
cell. Inter is retained **only** for running prose — page deks and source notes — which
is the legibility half of decision 2. Base size drops 15px → 11px.

Shape: every radius token becomes `0`; both shadow tokens become `none`. They are kept as
tokens rather than deleted so a component referencing one does not break.

Spacing: the existing scale is retained by name and tightened in value, so no component
has to change which token it names.

Note that `--base-font-px` sets `html { font-size: … }` and every `--size-*` and
`--space-*` token is expressed in `rem`. Dropping 15px → 11px therefore rescales the
whole system proportionally in one move, which is the intent — but it means the size and
spacing tokens must be re-derived against the new root rather than left at their current
`rem` values, or the interface will simply be the same design shrunk by 27%.

### Primitive layer (new, in `tokens.css`)

`.term-panel`, `.term-head`, `.term-grid`, `.term-cell`, `.term-key`, `.term-bar`. These
exist because `Panel`, `StatStrip` and `HeatTable` currently duplicate the same
header/body/footer shape three times in inline style objects, and the density rework has
to touch all three regardless. Afterwards density is tuned in one place, not eight.

### Components

| Component | Change |
|---|---|
| `Masthead`, `NavBar` | Command bar: amber wordmark, nav as spaced keys, active item an inverted amber block. Pills and `backdrop-filter` removed. |
| `TickerRail` | Tightened to the rail spec; 1px dividers; carries more symbols now the full width is available. |
| `PageHeader` | Compact title bar replaces the 1.9rem title over a 60ch dek. The dek survives as one muted line — several pages interpolate real values into it (row counts, week-ending dates), so it is not decoration. |
| `Panel` | Becomes `.term-panel`: amber label left, as-of + cadence right, source note in a footer strip. |
| `StatStrip` | Cards become a bordered monitor row of label/value/delta cells. |
| `ScreenCard` | Home-page destination cards become terminal list rows. |
| `HeatTable` | Structure unchanged; the heat wash is re-tuned — the current pale tints are built for white and vanish on black. |
| `ChartControls` | Segmented pills and chips become bracketed key toggles. |

Motion: `.card-link:hover` lift and `.rise` entrance are removed — both are product-UI
promises. `.flash` is **kept** and retuned: a value flashing on update is genuine
terminal behaviour. The `prefers-reduced-motion` block is unchanged.

### Charts and map

`web/src/theme/plotly.ts`: `paper_bgcolor`/`plot_bgcolor` to the panel ground, `GRID` to
`#1e232b`, `MUTED` and the font stack to the mono/muted values, and `SERIES` to the
lifted set below. `SERIES_CYCLE` keeps its order — navy-role first, grey-role last.

`web/src/components/map/VesselMap.tsx`: MapLibre style `carto-positron` →
`carto-darkmatter`.

### Series colours — roles kept, values lifted

| Role | Was | Becomes |
|---|---|---|
| primary | `#0f2a4a` navy | `#4d9fff` |
| secondary | `#5b9bd5` | `#9fd8ff` |
| seasonal median | `#e67e22` orange | `#ffa62b` |
| red | `#c0392b` | `#ff5a4d` |
| grey | `#95a5a6` | `#99a3ad` |
| band | `rgba(150,150,150,0.25)` | `rgba(160,170,185,0.18)` |

Navy remains "the primary series" and orange remains "the seasonal median", so a chart
here and the same chart in Streamlit still *mean* the same thing series-for-series. Only
the values differ, because navy at `#0f2a4a` on black is invisible.

## The contract that breaks

`plotly.ts`'s header comment currently claims "a chart exported from this app and one
exported from the Python side are indistinguishable". That stops being true and the
comment must be rewritten to state what is true instead: the two surfaces share the
series *roles*, not the values, and why.

Nothing on the Python side cross-checks `web/` — verified by grepping `tests/` for
`tokens.css`, `plotly.ts` and `web/src`. `tests/test_design_tokens.py` and
`tests/test_config_matches_design.py` pin `core/design.py` and `.streamlit/config.toml`
and are unaffected.

## Error handling and edge cases

- **Stale data** keeps its own louder treatment: an inverted amber bar, distinct from the
  amber-as-type used for panel labels. This is why amber-as-ink was chosen over
  amber-as-bars — the bar stays available for the warning.
- **Direction is carried by sign and colour, never colour alone.** The existing rule in
  `StatStrip` carries over unchanged; `--up`/`--down` on black are not a substitute for
  the `+`/`−`.
- **Empty and not-built states** (`NotBuiltYet`) get the panel treatment so a page with
  no data still reads as a panel with nothing in it, not as a hole.
- **Contrast is a constraint on the token set, not an afterthought.** This was written
  claiming `--faint` (`#6b7280`) on `#000` was ~4.7:1 and passing. Computed during
  planning, it is **4.34:1 and fails** — corrected to `#7d8590` (5.63:1). The error is
  left on the record because it is the argument for the test: eyes, and confident
  estimates, are bad at this. Any token that fails against its own ground is wrong and
  gets changed, not shipped.

## Testing

- **New:** `web/src/theme/tokens.test.ts`, in the same deliberately-literal style as
  `tests/test_design_tokens.py`: pin the dark series values, and assert every text token
  clears 4.5:1 against the ground it is used on. `web/` currently has only
  `format.test.ts` and `staleness.test.ts` and pins none of its design; the Python side
  pins its own literally, and this closes that asymmetry.
- **Unchanged:** all Python tests. If any of them go red, something touched a surface
  this design says it does not touch.
- **Manual:** every one of the 13 routes viewed at full width and at a narrow width
  before the branch is called done — the density change is the kind that looks right on
  the two pages you developed against and wrong on the eleven you did not.

## Risks

- **Density regret is expensive.** 11px is tight. It was chosen against rendered mockups
  rather than in the abstract, and it is one token, but eight components will be built on
  it. If it is wrong, it is cheapest to say so before the plan is executed.
- **Full-bleed** was expected to touch every page wrapper. It does not: `--measure` has
  exactly four consumers (`globals.css`'s `main`, `NavBar`, `PageHeader`, `TickerRail`),
  because the measure lives on `main` rather than in each route. Corrected during
  planning; this risk is much smaller than first recorded. The manual pass over all 13
  routes still stands, for the density change rather than for the width.
- **The maps and Plotly are the least certain.** A dark basemap and a dark plot ground are
  each one-line changes, but the charts were tuned on white and some may need per-chart
  attention.
- **Concurrent sessions.** Per the repo's standing rule, check `ListAgents` and
  `git status` before executing, and agree a file lane if a peer is live — a restyle
  touching `tokens.css` conflicts with almost anything else in `web/`.

## Definition of done

1. All 14 routes render in the terminal identity with no light-UI remnant (no radius, no
   shadow, no white ground, no pill).
2. `tokens.css` is the only place chrome values are defined; no component hardcodes a hex.
3. `web/src/theme/tokens.test.ts` passes, including the contrast assertions.
4. `pnpm test`, `pnpm lint` and `pnpm build` pass in `web/`.
5. The full Python test suite is unchanged and green.
6. `plotly.ts`'s header comment states the real cross-surface contract.
7. `web/CLAUDE.md` and `CHANGELOG.md` record the change, as the 2026-09-08 restyle did.
8. Per the user's standing rule, `/code-review` and `/security-review` are run on the
   branch diff before it is called done.
