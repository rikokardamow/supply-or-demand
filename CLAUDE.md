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
5. Charts use `core.theme` (Kardamow house style). No ad-hoc colours or styling.
6. British English in all prose, labels, and docstrings.
7. Small, typed, tested functions. Ask before adding a dependency or changing a schema.
8. End every session green: `pytest` passes, `ruff check .` clean, work committed.

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
- Tests: `pytest` | Lint: `ruff check .` | Types: `mypy core pipelines`
- New pipeline: scaffold under `pipelines/<source>/` with its own `CLAUDE.md`, client, and cassette test.

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
