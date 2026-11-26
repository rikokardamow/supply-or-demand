# PARKING.md

Open choices and ideas not taken yet. One line each; the long form is in `IMPROVE.md` (run 01, 2026-11-21).

- I-05 Keep first prints in the lake (vintage-aware `write_ts_long` and `read_ts_long`): here, in `desk-core` P-01, or both? `core/storage.py:182-183` overwrites today.
- I-06 GIE, ENTSO-E, ENTSOG, FRED, OPEC MOMR, Baker Hughes: the owner's register (`~/Projects/_runs/desk-core/RIGHTS.md`) reads them as class d; this repo's README says free. Read the API terms, ask for consent, or mark them d and take them off the public layer and the README chart.
- I-07 Replace Yahoo closes on the web front page, `/prices` and `/curves` with EIA daily spot (`RWTC`, `RBRTE`, Henry Hub); needs a key to record cassettes and a spot-versus-front-month decision.
- I-08 One unit vocabulary at ingest (`core/units.py`, normalise `BCF`, `MBBL`, `tb/d`, `USD`, `million barrels`), with a one-off rewrite of the owner's lake; reconcile with the artifact design system's spelled-out units.
- I-10 The data site cannot build offline (23 pages prerender from Supabase): say so in the README, or move to static export with Python-written JSON per PROJECT-STARTER section 3.
- I-11 Streamlit and artifact layers use red, green, dual axes, serif headings and Plotly: restyle to house style v4 from a `house_style.json`, or mark them legacy and set `STRICT_DESK = True` for the README charts.
- I-12 Merge or close 25 remote branches not on main: `fix/entsoe-forward-wind-forecast` (a September bug fix), `docs/readme-and-notes`, `chore/move-weather-spec` (then fix `docs/README.md:9`), `feat/sd-models` (EEX guard and four sources), the two `*-rebuilt` model pages, `feat/dash-app`; delete the seven rewritten-history branches; never push `spec/ibkr-curve`; commit or discard the uncommitted spec move in `~/Projects/energy-dashboard`.
- I-13 Retire or move what the private desks now own: trading analytics layer (specs 18-27), GRP module (specs 28.*), weather anomaly maps.
- I-14 Add `released_at` to `ts_long` from `core/calendars.py` (WPSR Wednesday 10:30 ET) once first prints are kept.
- After I-01: the `web/` pages still reference `fut.*.f01.close`; they fall to their empty state once the guard stops publishing Yahoo, until I-07 or another public-domain price lands.
- After I-02: run `uv run python -m pipelines.derived.unpublish_restricted` (dry run), read the counts, then `--apply`, against the owner's pooler connection.
- `infra/register_tasks.ps1` is a Windows Task Scheduler setup; PROJECT-STARTER says jobs run by hand.
- The GIE README chart caption has no licence line (`docs/img/eu_gas_storage.tex`); write one once I-06 is decided.
- After I-01: Frankfurter, GridStatus, JODI, OFAC, Adanos, Reddit, StockTwits, Polymarket, AIS and manual drops are class d in `core/rights.py` (terms not read, or no re-use statement found), so their rows, the `sanctions` and `vessel_latest` tables and the Brent `curve_settles` table stop being published. Read each terms page at source and change the class in `core/rights.py` to bring one back (`uv run python -m core.rights` rewrites `RIGHTS.md`).
- Before merging I-01 to I-04 and I-09: run the I-02 dry run against the pooler URL, read what is still served, then decide on `--apply`. Not run in the build session.
- After I-15: retake a dashboard screenshot for the README once I-07 (or another public-domain price) feeds the headline cards and I-11 settles the colours.
