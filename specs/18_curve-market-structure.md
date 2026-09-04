# Spec 18 — Curve & Market Structure

**Sources:** Bouchouev *Virtual Barrels* (storage boundaries, convexity, index-roll pressure); Newman *World of Oil Derivatives* (curve = prompt + chain of spreads; physical caps paper). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
The curve engine every later trading spec depends on: a futures-settlements pipeline (the one new upstream source in this layer), roll-adjusted nearby ranks, time-spread strips, convexity, a six-state curve-regime classifier, index-roll calendar and roll-pressure seasonality, Cushing-utilisation coupling, physical-differential bands. Page `18_curve.py`.

## Data
| Series | Source | Freq | Pipeline |
|---|---|---|---|
| `fut.<root>.<contract>.settle`, `.oi`, `.volume`; expiry in `series_meta` | CME (cl, rb, ho, ng), ICE (lco, g, tfm) | daily | **new** `pipelines/futures/` — two interchangeable clients behind one interface: `IBKRClient` (`ib_insync`, historical settles for the front 36 contracts per root; reuses Spec 07's gateway prerequisite) and `ManualCSVClient` (`data/manual/futures/settles_YYYYMMDD.csv`: date, root, contract, settle, oi, volume, expiry). Session A ships both; whichever is live is selected by `FUTURES_SOURCE` in `.env`. |
| `eia.w_epc0_sax_ycuok_mbbl` (Cushing stocks) | Spec 01 lake | weekly | exists |
| `eia.cushing_working_capacity` | Spec 14 (authorised) | semi-annual | exists / extend |
| `manual.platts.dated_brent`, `manual.platts.dfl_m1`, `manual.argus.wti_midland_diff`, `manual.argus.wti_houston_diff` | Platts/Argus manual drop | daily | `pipelines/manual_physical/` (Spec 19 owns; stub reader here) |
| `derived.index.gsci_roll_frac`, `derived.index.bcom_roll_frac` | computed from `core/calendars.py` | monthly | Session C |

## Sessions

### Session A — futures settlements pipeline
- `/new-pipeline futures`. Client interface `FuturesClient.get_settles(root, contracts, start, end)`; `IBKRClient` (ib_insync, 45 s timeout, per-contract failure isolation exactly like `pipelines/entsoe`), `ManualCSVClient`.
- `pull_history.py` (one-off, 1993→ where the source allows) and `pull_daily.py` (trailing 5-day re-pull, idempotent; verify by running twice).
- `series_meta` rows carry `expiry`, `tick_size`, `contract_unit`, `roll_rule`.
- Float64 regression test: a settle of `61.35` and a hand-written `0.35` read back exactly (v0.11 guard).
- Cross-check: one settle per root against the exchange's published daily bulletin.
- DoD: [ ] both clients behind one interface, [ ] daily pull idempotent (two runs, same row count), [ ] float64 regression test, [ ] live cross-check recorded here.

### Session B — `core/curve.py` nearby, spreads, convexity, regime
```python
def nearby_panel(contract_panel, expiries, roll_days_before_expiry=5, adjust="ratio") -> tuple[DataFrame, DataFrame, Series]  # adjusted f01..fn, unadjusted, roll_dates
def time_spreads(unadj) -> DataFrame       # s12=f1-f2, s13, s16, s1_12, s23; dec_dec = Dec(y)-Dec(y+1)
def annualised_slope(unadj) -> Series      # (f1-f12)/f1
def roll_yield(unadj) -> Series            # (f1-f2)/f2*12
def convexity(unadj, k=(1,2,3)) -> Series  # cv = F_k1 - 2*F_k2 + F_k3 ; also (1,3,6), (2,4,6)
def curve_regime(unadj, storage_cost_m1m2=0.60, lookback=252) -> DataFrame  # slope_sign, cv_sign, slope_pct, state
def transition_matrix(states) -> DataFrame
```
Regime states, evaluated in order: `super_contango` (s12 < −1.5×storage_cost and s1_12<0) → `super_backwardation` (s12 > p95(lookback) and s12 > 2.0) → `convex_contango` (s12<0, cv>0) → `concave_contango` (s12<0, cv<0) → `convex_backwardation` (s12>0, cv>0) → `concave_backwardation` (humped; s12>0, cv<0).
Write derived series to the lake (`derived.spread.*`, `derived.curve.*`) via a `pipelines/derived/curve.py` step run after the daily futures pull.
- Tests (synthetic data): rolls exactly 5 bdays before expiry; adjusted f01 has zero return on roll day; `convexity([80,79,78.5])=0.5`, `([80,79,77])=−1.0`; regime of `[80,79,78.5]`=`convex_backwardation`, `[80,81,81.5]`=`concave_contango`, `[80,81,82.5]`=`convex_contango`; transition-matrix rows sum to 1; no look-ahead (regime at *t* identical on data to *t* vs *t*+30).
- DoD: [ ] functions above, [ ] derived series in lake, [ ] all tests, [ ] no-look-ahead test.

### Session C — index-roll calendar, Cushing coupling, physical bands
```python
def roll_calendar(year, index) -> DataFrame   # GSCI: business days 5–9, 0.2/day; BCOM: 6–10, 0.2/day  (core/calendars.py)
def roll_window_flag(dates) -> Series[bool]
def roll_pressure_seasonal(s12, flag) -> DataFrame   # mean & t-stat of Δs12 inside vs outside window, by year
def cushing_utilisation(stocks_kbbl, working_cap_kbbl) -> Series   # forward-fill the semi-annual capacity; flag as step series
def utilisation_decile(util, years=5) -> Series
def physical_bands(diff, window=1260) -> DataFrame   # value, p05, p50, p95
def tas_window_flag(date, expiry) -> bool            # last two trading days before CL expiry
```
Store `derived.cushing.util` and `derived.cushing.util_decile` (consumed by Specs 19, 21).
- Tests: `roll_calendar(2026,'gsci')` January → bdays 5–9, fractions sum 1.0; BCOM 6–10; `cushing_utilisation(50000, 78000)=0.641±1e-3`; decile ∈ 1..10.
- DoD: [ ] functions, [ ] derived Cushing series, [ ] tests, [ ] Jan-2026 combined GSCI/BCOM roll dates shown correctly on page.

### Session D — page `18_curve.py` and theme primitives
`core/theme.py` additions: `curve_strip_chart` (multi-date curve + spread bars subplot), `regime_ribbon_chart`, `scatter_piecewise_fit_chart`, `bday_heatmap`. Existing `seasonal_range_chart`/`time_series_area_chart` reused where they fit.
Page tabs: Curve | Spreads | Convexity & Regime | Storage | Roll Calendar | Physical. Sidebar: root, as-of, storage-cost input. Top metric: days to next index roll. Every card caption names the source and any proxy.
Visualisation spec: (1) curve strip today vs −5bd/−20bd/−252bd with s12/s13/s16/s1_12 bars; (2) spread history with contango/backwardation shading, ±1σ/±2σ 252d; (3) cv with zero line and 5/95 pct; (4) regime ribbon under f01 + transition matrix table; (5) Cushing utilisation vs s12 scatter coloured by year with piecewise fit (<0.35, 0.35–0.75, >0.75) and Apr-2020 annotation, plus dual-axis time series; (6) year × business-day heatmap of Δs12 around roll windows; (7) DFL / Midland diff with bands and Newman's ±$5 physical-cap reference lines.
- DoD: [ ] page live in browser for every root, [ ] captions with sources/proxies, [ ] ruff/mypy/pytest green.

## Definition of Done (spec)
- [ ] Futures pipeline live from at least one client; `FUTURES_SOURCE` documented in `.env.example`.
- [ ] `core/curve.py` complete with tests above; derived spread/convexity/regime/Cushing series in the lake and refreshed by the daily pull.
- [ ] Page 18 live; one settle and the Cushing utilisation cross-checked against independent sources and recorded here.
- [ ] `specs/00_INDEX.md` status updated; CHANGELOG entry.

## Session A opener (paste into Claude Code, plan mode)
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md and specs/18_curve-market-structure.md. Plan Session A only: the `pipelines/futures/` pipeline with IBKR and manual-CSV clients behind one interface, history + daily pulls, series_meta expiries, float64 regression test, cassette test. Use /new-pipeline futures. Do not build core/curve.py yet.
