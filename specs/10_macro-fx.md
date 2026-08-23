# Spec 10 — Macro / FX Normalisation Layer (FRED + Frankfurter + Eurostat)

**Week 11 (alongside Spec 07) · Est. 4–6 h · Prereq: Spec 00. Feeds all pages.**

## Objective & alpha question
Separate real from nominal moves and currency effects: deflate energy prices, express series in
EUR and USD, and join demand-sentiment indicators. Question: *how much of a price move is macro/FX
vs energy fundamentals?*

## Data sources
1. **FRED** — `uv add fredapi`, free key (`settings.fred_api_key`), ~120 req/min.
   Series: `CPIAUCSL` (US CPI), `DTWEXBGS` (broad dollar), `DGS10`, `INDPRO`, `EA19CPALTT01GYM`
   (EA HICP via OECD on FRED — verify id in-session), plus any deflators you need.
2. **Frankfurter** — no key, ECB reference rates: `https://api.frankfurter.dev/v1/2018-01-01..?base=USD&symbols=EUR,GBP,TRY`
   (verify current host `frankfurter.dev` vs `frankfurter.app` in-session).
3. **Eurostat** — free REST (JSON-stat): ESI economic sentiment `ei_bssi_m_r2` (verify dataset code)
   for EU/DE/FR/IT/ES/IE.

## Data model
All → `ts_long`: `fred.cpiaucsl`, `fx.eurusd`, `estat.esi.DE`. FX daily; CPI/ESI monthly.

## Transformations (`core/macro.py` — shared helpers other pages import)
- `deflate(series, cpi_series, base_period)` → real terms.
- `to_currency(series, fx_series, target)` with frequency alignment (ffill FX to series dates).
- `align_freq(a, b, how='mean')` resampling helper.
- ESI YoY + z-scores.

## Visualisation spec (page `10_macro.py`)
1. Dual-axis: broad dollar (navy) vs WTI (light blue, from Spec 07; placeholder until then).
2. Real vs nominal crude (indexed 2018=100).
3. Energy-in-EUR vs energy-in-USD small multiples.
4. ESI heat-strip by country (monthly, diverging colours).

## Sessions

### Session A (weekday, 1 h) — FRED + Frankfurter
> Read NOTES.md, specs/10_macro-fx.md. Scaffold `pipelines/macro/`: fredapi wrapper + Frankfurter
> client (verify live host first) → ts_long; cassette tests (filter key). Acceptance: EURUSD for a
> known date matches ECB reference.

### Session B (weekday, 1 h) — Eurostat + helpers
> Eurostat JSON-stat client for ESI (verify dataset code live); implement core/macro.py helpers
> with hand-checked tests (deflation of a toy series; FX conversion with ffill).

### Session C (weekday, 1 h) — page + integration
> Page 10 with the four visuals (graceful placeholders where Spec 07 data absent). Weekly entrypoint.

## Definition of Done
- FRED/FX/ESI ingesting; `core/macro.py` helpers tested; page 10 live; at least one other page
  (01 or 07) using `to_currency` or `deflate`. Tests green.

## Stretch
- Trade-weighted energy import bill by country (Eurostat energy imports × prices).
