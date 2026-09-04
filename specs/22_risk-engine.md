# Spec 22 — Risk Engine

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Lyu, Qin, Ke, Yang & Chang (2024) *Energy Economics* 133 — GARCH-MIDAS (macro long-run component; world industrial production best; GPR degrades) + EVT/GPD tail; ≈2000-day rolling window; Kupiec UC and Christoffersen CC; historical simulation fails every test. Mack (Greeks, portfolio), Wengler (hedge effectiveness, basis, liquidity/strike availability). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
VaR/ES with backtesting, exposure trees, stress, margin/financing stress, hedge effectiveness. Exposes `realised_vol` and `garch_midas_evt_var` to Spec 21. Page `22_risk.py`.

## Data
Spec 18 adjusted f01 returns per root. Spec 10 FRED macro (`indpro`, plus world IP if added — else caption "US IP proxy for world IP"); Spec 06 OPEC/JODI production; OECD stocks (Spec 06 MOMR); EPU and GPR (manual CSV `data/manual/risk/`). Book and margins: manual `data/manual/risk/book.csv` (instrument, qty, side, strike, expiry, type) and `margins.csv` (SPAN outright/spread rates). Publication lags via `core/calendars.py` (IP ≈ +6 weeks).

## Sessions

### Session A — `core/risk.py` GARCH-MIDAS-EVT
Model: r = μ + √(τ_t g_t) ε; g GARCH(1,1) with unit unconditional variance; log τ_t = m + θ Σ_k φ_k(ω) X_{t−k}, Beta lag weights, K=36 (test 12/24/36), monthly X. EVT: POT on −z (z standardised residuals), threshold u = empirical 10% quantile, GPD MLE (ξ, ψ). VaR_q = μ + √(τg)·z_q with z_q from the GPD tail quantile; ES from the GPD mean-excess formula.
```python
def fit_garch_midas(r_daily, X_monthly, K=36) -> GMFit          # scipy MLE; two-step fallback (rolling RV as τ) with a visible warning
def evt_tail(z, u_q=0.10) -> dict                                # xi, psi, u, n_exceed
def var_es(fit, tail, q=(0.01, 0.025, 0.05)) -> DataFrame
def rolling_var(r, X, window=2000, refit_every=20) -> DataFrame  # long-run refit every 20 days, short-run daily
def kupiec_uc(exceptions, n, q) -> dict; def christoffersen_cc(exceptions, q) -> dict
def hs_var(r, window=500, q) -> Series                           # the control that fails
def compare_models(...) -> DataFrame                             # GM-IP-EVT, GM-OILPROD-EVT, GM-INV-EVT, GM-EPU-EVT, GM-GPR-EVT, GARCH-t, GARCH-EVT, HS × {1%, 2.5%, 5%} × {lower, upper}: exceptions, UC p, CC p, pass
def realised_vol(r, window=63) -> Series
```
Alert rule: UC or CC rejected at 5% in two consecutive quarters → model flagged on the card. Entrypoint `pipelines/derived/risk_refit.py`.
- Tests: Beta weights sum to 1±1e-9; `evt_tail` on 20,000 t(4) draws → ξ ∈ [0.15, 0.35]; Kupiec with 10/1000 at 1% → p≈1, 25/1000 → p<0.01; Christoffersen distinguishes alternating vs clustered exceptions; `rolling_var` shift test.
- DoD: [ ] model + backtests, [ ] tests, [ ] model card fields, [ ] refit entrypoint.

### Session B — desk risk (`core/risk_desk.py`)
```python
def exposure_tree(book, curves, greeks) -> DataFrame     # book→strategy→instrument; delta_bbl, spread_delta, crack_delta, vega, theta, gamma; tenor buckets M1-3 / M4-12 / >12
def portfolio_var(book, cov, method="parametric") -> dict
def stress(book, scenarios) -> DataFrame                  # scenarios.yaml
def margin_stress(book, margins, scenario, credit_line) -> dict   # IM+VM path, days-to-breach
def hedge_effectiveness(hedged, unhedged) -> dict         # 1 - var(h)/var(u); beta, R²; rolling 60d
def liquidity_check(book, adv, strike_oi) -> DataFrame    # position/20d ADV; strike availability (Wengler)
```
`scenarios.yaml`: 2008-07→12 path; 2020-04-20 (May WTI −$37.63 from $18.27; s12 to −$58); 2022-03-07 (Brent $139.13 intraday; s1_12 blow-out); parallel ±$10/±$20; front twist (f01 ±$5, f12 flat); contango flip (s12 +2 → −3); vol shock (ATM +15 pts, skew steepening); HH-proxy basis ±30% (Wengler).
- Tests: scenario 2020-04-20 on 100 lots long May WTI at $18.27 → −$5.59m ±1%; perfect hedge → effectiveness 1.0.
- DoD: [ ] functions, [ ] manual book/margins readers, [ ] tests.

### Session C — page `22_risk.py`
Theme additions: `var_fan_chart` (returns, VaR lines, exceptions, ES dashed), `pass_fail_matrix` (models × quantile/tail), `vol_decomposition_chart` (τ vs g, MIDAS weights), `gpd_qq_chart`, `treemap_chart`, `stress_waterfall` (extend `revision_waterfall`), `margin_path_chart`.
- DoD: [ ] page live with every card from Session A/B, [ ] green.

## Definition of Done (spec)
- [ ] GARCH-MIDAS-EVT live with the pass/fail matrix; HS shown failing. [ ] Desk pages. [ ] Refit registered with Spec 13. [ ] Index + CHANGELOG.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/22_risk-engine.md. Plan Session A: `core/risk.py` GARCH-MIDAS-EVT in scipy (no R), backtests, tests. Confirm which monthly macro series Spec 10 already holds before designing the MIDAS inputs.
