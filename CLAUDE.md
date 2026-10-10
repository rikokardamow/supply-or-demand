# Energy Dashboard — Claude Code Guide (root)

## What this is
Solo-analyst energy/macro research dashboard (publication: Kardamow). Python monorepo:
`pipelines/` ingest per-source data → DuckDB + Parquet lake (`data/`) → Streamlit multipage app (`apps/dashboard/`).
Specs for each sub-project live in `specs/`. Always read the relevant spec before coding.

## Golden rules
1. Never print, log, or commit API keys. All secrets via `core.settings` (pydantic-settings) from `.env`.
2. Pipelines write to `data/` in canonical schemas. Dashboard pages READ the lake, never call APIs.
3. All scalar time series conform to `ts_long`; directional data to `flows`. See `core/schemas.py`.
4. Seasonal maths (median/range/corridor) ALWAYS exclude 2020. Use `core.seasonal` — never reimplement.
5. Charts use `core.theme` (Kardamow house style), whose colours and fonts are bound
   from `core.design` (the token source). No ad-hoc colours or styling.
6. British English in all prose, labels, and docstrings.
7. Small, typed, tested functions. Ask before adding a dependency or changing a schema.
8. End every session green: `pytest` passes, `ruff check .` clean, work committed.
   See § Code review procedure for the full order.

## Stack
Python 3.12, uv, pandas (+polars where it earns its keep), duckdb, plotly, streamlit,
pydantic + pydantic-settings, requests, websockets (AIS only). Lint: ruff. Types: mypy.
Tests: pytest + vcrpy cassettes in `tests/cassettes/`.

## Canonical schemas (core/schemas.py)
- `ts_long(series_id, source, ts, value, unit, geo, freq, revision_date)`
- `flows(source, from_node, to_node, value, unit, ts, mode)`
- `vessel_positions(mmsi, ts, lat, lon, sog, cog, nav_status, ship_type, draught)` + `vessel_static(mmsi, imo, name, ship_type, dims)`
- `events(event_id, ts, headline, source, url, tags, geo, commodity, severity)`

## Commands
- Run app: `streamlit run apps/dashboard/app.py`
- Tests: `pytest` | Lint: `ruff check .` | Types: `mypy core pipelines infra apps`
- New pipeline: scaffold under `pipelines/<source>/` with its own `CLAUDE.md`, client, and cassette test.

## Code review procedure
Run these in order — cheapest first, and never skip step 1.
1. `ruff check .` → `mypy core pipelines infra apps` → `pytest`. Fix everything here before
   asking an agent to read the diff; review agents waste effort on what the linter already knows.
   `mypy` is the gate. Pyright runs live in the editor via the `pyright-lsp` plugin and is
   stricter by default — treat its extra findings as signal, not as a merge blocker.
2. `/code-review high` on the working diff. `--fix` applies findings; `--comment` posts them
   inline on a PR. Use `/simplify` instead when the diff is correct but overgrown.
3. Targeted agents from `pr-review-toolkit` (`/review-pr`, or invoke one directly):
   - `silent-failure-hunter` — required on any pipeline or ingest diff. A swallowed exception
     in the DuckDB/Parquet path becomes a quietly wrong number on a published chart.
   - `pr-test-analyzer` — new pipeline code, checked against its cassette.
   - `type-design-analyzer` — changes to `core/schemas.py` invariants.
   - `code-reviewer` — reads this CLAUDE.md and checks the diff against the golden rules.
4. `/security-review` before merging anything that touches `infra/`, `railway.toml`,
   `core/settings.py`, or a new API client — i.e. anywhere a key could leak (golden rule 1).
5. `/code-review ultra` before a large merge to `main` (multi-agent cloud review of the branch;
   user-triggered and billed, so ask first).
6. `/superpowers:requesting-code-review` when closing out a spec — it reviews against the
   spec's acceptance criteria rather than the diff alone.

Further plugins worth adding (`claude plugin install <name>@claude-plugins-official`):
`claude-security` (deeper, slower vulnerability scan than step 4), `duckdb-skills`
(query-correctness guidance).

## Data release calendar (schedule pulls around these)
EIA WPSR Wed 10:30 ET · EIA gas storage Thu 10:30 ET · AGSI+/ALSI+ daily ~19:30 CET ·
ENTSO-E day-ahead ~12:45 CET · Baker Hughes Fri ~noon CT · OPEC MOMR ~11th–14th ·
JODI ~20th · CFTC COT Fri 15:30 ET.

## Chart house style (core/theme.py, template "kardamow")
White background; navy `#0f2a4a` primary series; light blue `#5b9bd5` secondary; red `#c0392b`
accents/highlights; orange `#e67e22` seasonal median; grey `rgba(150,150,150,0.25)` seasonal band;
light grid `#e6e6e6`; horizontal legend top-left; direct annotations near last point
("Latest / YoY / vs median") instead of relying on legends; dual axes navy-left / light-blue-right.
Charts use the Inter font (`template.layout.font`) to match the app's own typography.

## Design system (published pages, slides and workbooks)
Applies to everything `apps/artifacts/` produces — the claude.ai artifact pages, the
PowerPoint briefing and the Excel workbook — and extends the chart house style above;
where the two overlap they must agree, and `core/design.py` stays the token source.
- **Ground and ink.** Navy `#0f2a4a` on white. Light theme only, as in the Streamlit app.
  Headings on the Lora stack, everything else (and every number) on the Inter stack;
  pages fall back to Georgia / Segoe UI because artifacts cannot load those webfonts.
- **Series.** Navy is the primary series, light blue `#5b9bd5` the secondary. A third
  series is grey; red is for stale flags only, never a data series.
- **Two units, two axes.** When an exhibit compares two units it is dual-axis: navy left,
  light blue right, each axis titled and tinted to its series. PowerPoint has no second
  axis through python-pptx, so the deck stacks two charts on one date axis instead.
- **Seasonal range bands.** Five-year minimum to maximum as a grey band, dotted orange
  median, prior year in light blue, current year in navy drawn last so it sits on top.
  The window is the five calendar years before the current one, passed to
  `core.seasonal.seasonal_stats` (golden rule 4 — 2020 is still dropped, and the label
  says "ex-2020" when the window reaches it). This is narrower than the Streamlit app's
  default 2018-onwards band; the two will show different medians for the same series.
- **Averages.** Every time-series exhibit carries MA20, MA100 and MA200 of its lead series
  (means of the last 20, 100 and 200 observations, computed over the whole lake history,
  not the chart window) and a five-year average: a flat line on a time axis, the mean of
  the band's years on a seasonal chart. Thin dashed lines behind the data: slate ramp
  `MA_SHORT`/`MA_MID`/`MA_LONG` from `core/design.py`, the five-year average in orange.
  A window the history cannot fill is left out, never drawn from fewer observations.
  Bar charts, forecast or scenario series and the forward curve get none. Every point is
  in the workbook's `moving_averages` sheet.
- **Annotated turning points.** Each time-series exhibit labels its window high and low
  with value and date, and seasonal charts also label the latest point with its distance
  from the median. Labels are computed, never typed.
- **Takeaway.** Two lines above every chart, generated from the same rows the chart draws.
- **Source line.** Under every chart: provider · lake table and series · last observation
  · pipeline run (`ts_long.revision_date`, or the Parquet write time for `flows`).
- **Stale flag.** `No data since <date>` in red once the last observation is more than
  two release cycles old. A gap is shown, never filled or hidden.
- **Numerals.** All quantities as numerals with units (`424.5 million barrels`, `7 Sep
  2026`); thousands separators; shares compared in percentage points, not percent of a
  percent.
- **No boxes.** Heading over a hairline rule, as `components.section` does; no cards,
  shadows or rounded panels.
- **One spec, every surface.** An exhibit is defined once in `apps/artifacts/exhibits.py`.
  `static/charts.js` draws it on the pages, `office.py` on slides and sheets, and
  `apps/artifacts/figures.py` as a Plotly figure for the Streamlit app. In the app, use
  `components.exhibit.exhibit(spec)` (heading, stale flag, takeaway, chart, source line)
  with specs from `components.exhibit.load_book()`; the Briefing page shows them all.
  Change a chart in `charts.js` and `figures.py` together.

## Dashboard layout — institutional look
Explicit light theme locked via `.streamlit/config.toml` (white canvas, Inter font) —
never rely on the viewer's OS/browser dark-mode preference. The navy sidebar is gone:
`apps/dashboard/app.py` paints a centred "Kardamow" wordmark masthead (the document's
only `<h1>`) over a hairline rule, with grouped top navigation (`st.navigation`,
`position="top"`) beneath it in place of the old filename-derived sidebar. Every page
opens with `components.section.page_header(title, as_of=..., freshness=...)` (`<h2>`,
Lora heading face, caps meta line) and wraps each chart or table in
`components.section.section(title)` (`<h3>` + hairline rule) instead of the old bordered
`card()`, which no longer exists — group multiple related charts under a plain
`st.subheader` label with one `section(...)` per individual chart underneath, matching
the existing pages. `components.section` also has
`kpi_row`, `empty_state`, and `source_note` (provenance/units/caveats caption under a
chart) for the same purpose card() used to serve piecemeal. Headings use the Lora stack
(`core.design.HEADING_STACK`); axis ticks, legends, data labels and every other in-chart
string stay on the Inter body stack (`core.design.BODY_STACK`) — numbers never render in
the serif. No chart paints its own title: `section()`/`page_header()` own the heading,
so `core/theme.py` builders no longer take a `title` parameter (except where a title
string is genuine in-plot content, e.g. `gauge_chart`'s `go.Indicator` label) and no page
should call `fig.update_layout(title=...)` directly — where a chart's own title carried
real information the static section heading can't (a date, a selected value, an
averaging window), surface it via a visible widget, `st.caption`, or `source_note`
instead of repainting it inside the plot. Maps use `go.Scattermapbox` with the free
`"open-street-map"` style (no Mapbox token) — never `go.Scattergeo`, which only renders a
flat continent outline. Never pass `use_container_width` to `st.plotly_chart`/
`st.dataframe`: Streamlit deprecated it (removal was scheduled for after 2025-12-31) in
favour of `width`, whose default is already `"stretch"` — so the argument is now pure
noise. Pass nothing for a full-width element, or `width="content"` to size to content.

## When unsure
Prefer the smallest change that satisfies the spec's acceptance criteria. If an API responds
unexpectedly, record the real response as a cassette and adapt — do not guess schemas.

## Trading analytics layer (Specs 18–27)
Conventions in `specs/00_TRADING_CONVENTIONS.md` (read before any session on these specs).
Analytics live in flat `core/<topic>.py` modules; ingestion in `pipelines/`; pages via
`/new-page`. Do not create a separate package tree. Series IDs follow the lake's lowercase
dotted style. Spreads never from back-adjusted series. Every model card shows window / refit
/ OOS status / exceptions / break date. Published literature benchmarks are shown beside repo
estimates with the deviation.

## General coding behaviour

Behavioural guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgement.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.