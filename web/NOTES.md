@AGENTS.md

## Design system — the terminal

`web/` is a Bloomberg-style terminal: black ground, one monospace family,
amber as the sole accent, zero radius, no shadow, full-bleed (`--measure` was deleted
outright, not just unreferenced). `web/src/theme/tokens.css` is the only place chrome
values live — components reference `var(--x)`, never a hardcoded colour, radius or
font. A primitive layer sits on top of the tokens: `.term-panel`, `.term-head`,
`.term-grid`, `.term-cell`, `.term-key`, `.term-bar`, `.term-table`. Reach for one of
these before writing a bespoke wrapper.

**Amber is rationed.** It is type on a dark strip, not a fill. A solid amber block is
spent on exactly two things: the active nav item (`.term-key[aria-current="page"]`)
and a stale-data badge. If amber became the ground of every panel header there would be
nothing louder left for a warning to use.

**Direction is carried by sign and colour together, never colour alone.** A figure that
is up or down always shows its sign (`+`/`-`) as well as `--up`/`--down` — colour blindness
and a black-and-white printout must not lose the information a green or red tint carries
on its own.

**The contrast floor is 4.5:1**, enforced by `web/src/theme/tokens.pins.test.ts`
against every ground a token actually paints on. It has already caught two tokens
picked by eye and wrong: `--faint` at `#6b7280` was 4.34:1 and is now `#7d8590`
(5.63:1); `--down` at `#ea3943` was 4.4951:1 and is now `#ee4a56`. Do not edit
`--navy-rgb`/`--red-rgb` as literals — the test derives their expected value from
`--navy`/`--red` itself, so a retuned hex without a matching rgb triple fails loudly
instead of silently drifting.

**Every `var(--x)` referenced under `src/` must resolve against `tokens.css`.**
`web/src/theme/tokens.test.ts` (pre-existing — do not edit it) walks the tree and fails
on any token that isn't defined; it is what caught five tokens that had been rendering
as nothing on the site while it was hosted, before this restyle. Adding or renaming a
token without updating its callers fails this test, which is the point.

**Charts and the map extend `theme/plotly.ts`'s `baseLayout()` and never set their own
ground.** Only `plotly.ts` sets `paper_bgcolor`/`plot_bgcolor`; a chart component that
painted its own background could drift from the terminal ground or reintroduce a white
chart on a black page.

**The series share roles with `core/design.py`, not values.** Navy is still the
primary series, orange is still always the seasonal median, and the cycle order is
unchanged — but navy at `#0f2a4a` (the Python/Streamlit value) is invisible on black,
so every series colour here is re-derived at a luminance that survives a dark ground
(`--navy: #4d9fff`, `--red: #ff5a4d`, etc.). A chart drawn here and the same chart
exported from the Streamlit app therefore read the same story but are not painted the
same colour — that split is deliberate, not drift.
