# Energy Dashboard — development notes

## What this is
Solo-analyst energy/macro research dashboard (publication: Kardamow). Python monorepo:
`pipelines/` ingest per-source data → DuckDB + Parquet lake (`data/`) → Streamlit multipage app (`apps/dashboard/`).
Specs for each sub-project live in `specs/`. Always read the relevant spec before coding.

## Golden rules
1. Never print, log, or commit API keys. All secrets via `core.settings` (pydantic-settings) from `.env`.
2. Pipelines write to `data/` in canonical schemas. Dashboard pages READ the lake, never call APIs.
3. All scalar time series conform to `ts_long`; directional data to `flows`. See `core/schemas.py`.
4. Seasonal maths (median/range/corridor) ALWAYS exclude 2020. Use `core.seasonal` — never reimplement.
5. Charts use `core.theme` (Kardamow house style). No ad-hoc colours or styling.
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
- Tests: `pytest` | Lint: `ruff check .` | Types: `mypy core pipelines infra`
- New pipeline: scaffold under `pipelines/<source>/` with its own `NOTES.md`, client, and cassette test.

## Code review procedure
Run these in order — cheapest first, and never skip step 1.
1. `ruff check .` → `mypy core pipelines infra` → `pytest`. Fix everything here before
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
   - `code-reviewer` — reads this NOTES.md and checks the diff against the golden rules.
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

## Dashboard layout — institutional look
Explicit light theme locked via `.streamlit/config.toml` (white canvas, dark-navy sidebar,
Inter font) — never rely on the viewer's OS/browser dark-mode preference. Every chart
section is wrapped in `apps.dashboard.components.card.card(title)` (a bordered
`st.container`) instead of a bare `st.subheader` — group multiple related charts under a
plain `st.subheader` label with one `card(...)` per individual chart underneath, matching
the existing pages. Maps use `go.Scattermapbox` with the free `"open-street-map"` style
(no Mapbox token) — never `go.Scattergeo`, which only renders a flat continent outline.

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