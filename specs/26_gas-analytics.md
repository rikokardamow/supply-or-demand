# Spec 26 — Gas Analytics

**Sources:** *Understanding Natural Gas Markets* primer (hubs, basis, bid week, storage, degree days); *Trading and Price Discovery for Natural Gas* (oil indexation → gas-on-gas; hub churn; LNG arbitrage; renegotiation waves); Wengler (HH proxy-hedge basis risk); Mack. Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Analytics over gas data already in the lake (Specs 02, 05, 08, 10) plus Spec 18's NG/TTF/NBP/JKM curves: LNG netbacks, US basis map, storage-spread economics, EU fill trajectory, indexation tracker, gas strategies. Page `26_gas_analytics.py`. Existing pages 02 and 05 are untouched. (Do-not-build list: no TTF forward-curve *pipeline* is built here — TTF comes through Spec 18's futures pipeline as one more root.)

## Data
Spec 18: ng, tfm, nbp, jkm curves. Spec 10: `fx.usd_eur`, `fx.usd_gbp`, HH spot. Spec 05: EIA storage (L48 + regions), LNG exports. Spec 02: AGSI fill %, injection/withdrawal. Spec 08: HDD/CDD actual, forecast, normal. Manual (`data/manual/gas/`): basis hubs (Waha, Chicago, SoCal, Algonquin, Transco Z6, Dominion S, AECO, HSC), bid-week indices, liquefaction fee, shipping $/MMBtu by route, IGU contract mix, pipeline capacity-add calendar. Flows from Spec 03 ENTSOG.

## Sessions

### Session A — `core/gas_analytics.py` conversions, netbacks, basis, storage economics
Conversions: TTF €/MWh → $/MMBtu = px × EURUSD × 0.29307; NBP p/therm → $/MMBtu = px/100 × GBPUSD × 10.
```python
def hub_board(as_of) -> DataFrame                       # spot, m1, m6, m12, winter/summer strips, 1y change
def churn(traded, throughput) -> Series
def lng_netback_us(jkm, ttf, hh, liq_fee, ship_asia, ship_eu, boiloff) -> DataFrame   # netback = dest − ship − boiloff; margin = netback − (1.15·HH + liq_fee); cancellation flag when dest − ship < 1.15·HH
def basis_map(hubs, hh) -> DataFrame                    # basis, pct_rank_3y, constraint_flag (|z|>2 for ≥5 days)
def storage_band(series) -> DataFrame                   # core.seasonal, ex-2020 (do not duplicate Spec 19's wrapper — import it)
def eu_fill_trajectory(fill_pct, target_date, target_pct) -> DataFrame
def degree_day_anomaly(hdd, cdd, normal) -> DataFrame
def storage_spread_economics(F_sum, F_win, inj_cost, wd_cost, carry_rate, days) -> DataFrame   # summer–winter and Mar/Apr
def indexation_tracker(oil_px, slope, const, ttf_usd, jkm) -> DataFrame   # gap_pct; renegotiation-pressure flag when |gap|>30% for >6m
def bidweek_vs_daily(bidweek, daily) -> DataFrame
```
Derived: `derived.gas.netback.*`, `derived.gas.basis.*`, `derived.gas.storage_spread.*`.
- Tests: TTF 30 €/MWh at 1.10 → 9.67±0.01; NBP 80 p/therm at 1.30 → 10.40; netback case JKM 12, HH 3, liq 2.75, ship 1.5 → margin_asia ≈ 4.30 − boiloff; fill-trajectory gap 0 on the linear path; constraint flag needs ≥5 consecutive days; net = spread − costs exactly.
- DoD: [ ] functions + derived series, [ ] manual_gas reader, [ ] tests, [ ] one netback input cross-checked against a published LNG cost breakdown.

### Session B — strategies (`core/gas_strategies.py`, via core.backtest)
Summer–winter storage spread (enter when economics net > 1σ and storage z < 0; exit at net < 0 or Sep 30; 2–5% per leg); Mar/Apr widow-maker fade (spread > p90 3y and storage z > +1; never when z < −1); basis constraint trade (short constrained basis when capacity add dated within 60 days; long Algonquin winter basis on HDD anomaly > +1σ); JKM–HH convergence (margin_asia > 2× 3y median and EU/Asia storage z > +1); HH-proxy basis-risk card (rolling basis vol + Spec 22 hedge effectiveness) for any physical position hedged with HH.
- Tests: entry/exit rules on synthetic paths; positions lagged.
- DoD: [ ] strategies registered in Spec 21's registry, [ ] backtest cards with weather-dominance caption.

### Session C — page `26_gas_analytics.py`
Theme additions: `netback_stack_chart` (HH×1.15, liquefaction, shipping, boil-off vs JKM/TTF; best-destination ribbon; cancellation shading), `basis_geo_map` (reuse `news_map.py`'s Scattermap approach), `required_path_chart`. Reuse `seasonal_range_chart`, dual-axis primitives from Spec 08.
Visualisation spec: hub board + four curves in $/MMBtu; netback stack; basis map + constraint table; storage bands (US + EU vs required path); degree-day anomaly vs prompt; storage-spread economics vs actual; indexation gap + contract-mix pie; bid week vs daily.
- DoD: [ ] page live, [ ] green.

## Definition of Done (spec)
- [ ] Sessions A–C. [ ] Index + CHANGELOG.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/26_gas-analytics.md, and pipelines/gie/NOTES.md + pipelines/weather/NOTES.md for existing series IDs. Plan Session A: `core/gas_analytics.py` importing Spec 19's seasonal wrapper, `pipelines/manual_gas/` reader, derived series, tests.
