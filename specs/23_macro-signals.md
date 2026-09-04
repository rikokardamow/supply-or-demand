# Spec 23 — Macro & Cross-Asset Signals

**Sources:** Yamarone *Trader's Guide to Key Economic Indicators* (ISM derived signals, payroll recession rule, ISM Prices–WTI link); Ma, Li & Zhou (2024) *IREF* 96 — GFU predictive regression; published in-sample R² 13.63%, OOS 11.32% (SSRN version 5.13%/3.27% — show both); beats ≈23 competitors; Clark–West; mean-variance economic value. Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Extends Spec 10's page 10 (Macro & FX) with Yamarone-derived signals and a monitored GFU overlay exporting a monthly ±1 tilt to Spec 21. New page `23_macro_signals.py` (page 10 stays as is).

## Data
Spec 10 FRED (35 series; add via the existing FRED client: `napm`, `napmnoi`, `napmii`, `napmpri`, `payems`, `indpro`, `tcu`, `dgs10`, `dgs2`, `t10y3m`, `vixcls`, `baa10y` — confirm each live, per Spec 10's own lesson). Manual (`data/manual/macro/`): GFU index (Caggiano–Castelnuovo), consensus/release calendar (date, indicator, consensus, actual), Kilian index, EPU, GPR, China IP/imports. Oil monthly returns from Spec 18 f01.

## Sessions

### Session A — `core/macro_signals.py` Yamarone board
```python
def ism_no_minus_inv(no, inv) -> Series                  # vs real GDP yoy
def ism_no_minus_prices(no, prices) -> Series            # NO-P; threshold −20
def payroll_recession_rule(payems) -> Series[bool]       # three consecutive negative months
def ism_prices_vs_wti(prices, wti) -> dict               # rolling 36m corr, cross-corr ±6m
def surprise_z(actual, consensus, history=36) -> Series
def persistence_diag(x) -> dict                          # AR(1) rho, DF-GLS, half-life — shown beside every candidate predictor
def yield_curve_regime(t10y3m) -> Series
```
- Tests: payroll rule fires only after three consecutive negatives; NO-P flag flips exactly at −20; `persistence_diag` on AR(1) ρ=0.98 → ±0.03.
- DoD: [ ] functions, [ ] FRED additions confirmed live, [ ] tests.

### Session B — GFU predictive regression (`core/predictive.py`)
```python
def predictive_regression(r_next, x, hac_lags=6, B=2000) -> dict   # OLS, Newey–West t, R²_IS, wild-bootstrap p
def oos_forecast(r, x, train_min=120) -> DataFrame                  # expanding window, monthly
def r2_oos(f, bench, actual) -> float                               # Campbell–Thompson
def clark_west(f, bench, actual) -> dict
def horse_race(r, predictors: dict) -> DataFrame                    # beta, NW-t, R²_IS, R²_OOS, CW p, AR(1) rho
def economic_value(f, r, gamma=3, w_bounds=(-0.5, 1.5)) -> dict     # CER gain, Sharpe
def gfu_tilt(forecast) -> Series                                    # +1/−1 monthly; disabled when rolling 24m OOS R² < 0
```
Predictor set (≈23): ΔGFU, GFU, DP, term, default, TB3, INF, VIX, LTR, Kilian, EPU, GPR, oil supply growth, OECD stocks growth, DXY, MSCI world, copper, BDI, ISM PMI, NO−P, payroll change, HDD/CDD anomaly (Spec 08), rig change (Spec 06). Writes `derived.tilt.gfu`.
- Tests: `r2_oos` = 0 when forecast equals benchmark; Clark–West rejects on a simulated true predictor (β=0.3, T=400) and ≤10% of 200 noise sims; `oos_forecast` month m uses data through m−1 only.
- DoD: [ ] functions, [ ] tilt in lake + monthly entrypoint, [ ] model card.

### Session C — page `23_macro_signals.py`
Theme additions: `threshold_line_chart` (NO−P with −20), `recession_shaded_timeline`, `cross_correlogram`, `oos_sse_difference_chart`, sortable horse-race table with persistence column flagged red when ρ>0.95. Reuse Spec 10's dual-axis primitives.
- DoD: [ ] page live, [ ] both GFU R² figures displayed beside the repo estimate.

## Definition of Done (spec)
- [ ] Sessions A–C; tilt registered with Spec 13. [ ] Index + CHANGELOG.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/23_macro-signals.md and pipelines/fred/CLAUDE.md. Plan Session A: confirm each new FRED ID live, extend the Spec 10 pull, build `core/macro_signals.py` with tests.
