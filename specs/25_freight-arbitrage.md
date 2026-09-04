# Spec 25 — Freight & Arbitrage

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Adland & Alizadeh (2018) *Transportation Research E* 118:20–33 — TC and FFA cointegrated; TC priced above FFA (convenience yield of secured tonnage + counterparty premium); ARMA-X model of the differential with term-structure level/slope, stress, vessel specs, contract terms; DWT ≈ 0.46/0.63/1.40% per 1,000 DWT (Capesize/Panamax/Supramax); Pacific-delivery discount ≈ 13.02/11.40/15.36%; duration negative in backwardated freight; extension option positive; differential trading is statistical arbitrage only. Imsirovic (crude arbs, EFS). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Physical-vs-paper freight model, hedge-ratio adjustment, landed-cost arbitrage monitors that also feed Spec 26's LNG netbacks. Page `25_freight.py`. Note: the analytics layer's do-not-build list excludes Baltic indices as a *scheduled* source — this spec takes them as manual drops only.

## Data (all manual, `pipelines/manual_freight/`, `data/manual/freight/`)
Baltic indices and tanker routes (BDI, BCI 5TC, BPI 4TC, BSI 10TC; TD3C, TD20, TD25, TC2, TC5, TC14 in WS and $/day), FFA curves and 6m/12m strips, TC fixtures (date, vessel, dwt, built, delivery_region, duration_m, rate, options), freight cost table (route, $/bbl or $/t by class), WS flat rates. Crude/product prices, EFS, Dated–Dubai from Specs 10/18/19. AIS flows from Spec 11 (if present) for cross-check.

## Sessions

### Session A — `core/freight.py` TC–FFA model
```python
def ffa_equivalent(ffa_curve, start, duration_m) -> float
def differential(tc, ffa_eq) -> Series                         # ln(TC) − ln(FFA_eq)
def cointegration_test(tc, ffa) -> dict                        # Engle–Granger + Johansen
def armax_differential(d, X) -> Results                        # statsmodels SARIMAX(order=(p,0,q), exog=X)
def hedge_ratio_adjust(base, vessel, coefs) -> float           # × (1+dwt_effect) × (1−pacific_discount) × duration/option terms
def fair_differential(model, X_now) -> float
def differential_signal(d, fair, band=1.0) -> Series           # +1: TC rich; −1: FFA rich
```
X: log FFA level, term slope (12m−1m)/1m, spot percentile, stress (VIX or BDI vol), ln(DWT/benchmark), age, Pacific dummy, duration, option dummy. Card shows estimated coefficients beside the published anchors with CI and flags deviation >50%.
- Tests: `ffa_equivalent` over 6 months = mean of six; ARMA-X on simulated data recovers a DWT coefficient of 0.005 within ±0.002; `hedge_ratio_adjust` Capesize +10,000 DWT, Pacific ≈ base × 1.046 × 0.8698; cointegration rejects on a cointegrated pair, not on independent random walks.
- DoD: [ ] manual_freight reader + fixture test, [ ] model, [ ] tests.

### Session B — landed-cost arbs (`core/arb.py`)
```python
def ws_to_per_bbl(ws, flat_per_t, bbl_per_t=7.33) -> float
def landed_cost(fob, freight_bbl, insurance, losses_pct, financing_days, rate, port_fees) -> float
def arb_transatlantic(wti_houston, dated_brent, freight_bbl) -> Series      # >0 open US→EU
def arb_east_west(dated_brent, dubai, efs, freight_bbl) -> Series
def arb_products(route, origin_px, dest_px, freight_bbl) -> Series          # TC2, TC5, TC14
def arb_persistence(arb) -> Series                                           # consecutive days open
```
- Tests: `ws_to_per_bbl(100, 20)` ≈ 2.73; hand-computed transatlantic case sign.
- DoD: [ ] functions + tests, [ ] Spec 11 AIS cross-check caption if flows exist.

### Session C — page `25_freight.py`
Theme additions: `coefficient_comparison_table`, `arb_board_chart` (net arb with zero line + stacked freight-cost bar), `freight_term_structure_chart`.
Visualisation spec: TC vs FFA-equivalent + differential with fair band; coefficient table; differential signal backtest (core.backtest, basis-risk haircut, caption "statistical arbitrage — not riskless"); arb boards (transatlantic, east–west, TC2, TC5); freight term structure and spot percentile.
- DoD: [ ] page live, [ ] green.

## Definition of Done (spec)
- [ ] Sessions A–C. [ ] Index + CHANGELOG.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/25_freight-arbitrage.md. Plan Session A: `pipelines/manual_freight/` reader with a checked-in fixture CSV (synthetic, clearly labelled), `core/freight.py`, tests.
