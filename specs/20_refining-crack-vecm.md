# Spec 20 — Refining Economics & Crack Spread Forecasting

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Murat & Tokat (2009) *Energy Economics* 31:85–90 — VECM of WTI spot on 3:2:1 crack spread futures; structural break **April 2003** (not September — a correction on record); unidirectional Granger causality crack → spot; both futures VECMs beat the random walk; crack model "almost as good as" crude futures. Newman (crack mechanics). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Crack boards (superseding the deferred IBKR-based Spec 07 for crude/product cracks — Spec 07 remains for anything IBKR-only) plus a monitored VECM pipeline with an error-correction trading signal. Page `20_cracks.py`.

## Data
Spec 18 unadjusted nearby for cl, rb, ho, g, lco. Spec 10: `fred.dcoilwtico` (WTI spot), `fred.dcoilbrenteu`. Manual: Singapore GO/jet/380 (`pipelines/manual_physical/`). Monthly aggregation = last business day (paper is monthly).

## Sessions

### Session A — `core/cracks.py` boards
Units: RB/HO $/gal × 42; ICE gasoil $/t ÷ 7.45.
```python
def crack_321(cl, rb, ho) -> Series   # (2*rb42 + ho42 - 3*cl)/3
def crack_211(cl, rb, ho) -> Series   # (rb42 + ho42 - 2*cl)/2
def crack_rbob(cl, rb); crack_ho(cl, ho); crack_gasoil_nwe(lco, g_bbl); crack_sg_go(dubai, sg_go)
def crack_board(as_of) -> DataFrame   # crack, spot, m1, m2, m6, seasonal_5y_mean (ex-2020 via core.seasonal), pct_rank_5y
def crack_seasonal_heatmap(crack) -> DataFrame   # year × month
```
Derived series `derived.crack.<name>.<tenor>` written daily.
- Tests: `crack_321(70, 2.20, 2.40)=28.53±0.01`; unit conversions; RBOB pre-2006 splice flagged (unleaded → RBOB contract change).
- DoD: [ ] boards + derived series, [ ] tests, [ ] one crack cross-checked against EIA's published 3-2-1.

### Session B — `core/vecm.py` Murat & Tokat pipeline
```python
def unit_root_tests(y) -> dict                        # ADF (AIC lags), PP, KPSS → I(1) verdict
def structural_break(df) -> dict                      # Bai–Perron (ruptures) + Andrews sup-F; must recover April 2003 on the 1993–2008 sample
def johansen(df, det_order=0, k_ar_diff=p) -> dict    # trace, max-eig, 5% cvs, rank
def fit_vecm(df, rank=1, k_ar_diff=p) -> VECMResults  # statsmodels; store alpha, beta, Gamma
def granger(df, maxlag=p) -> DataFrame                # both directions
def forecast_eval(model, test_window, h=1) -> dict    # rolling-origin; RMSE, Theil U, Diebold–Mariano vs random walk and vs crude-futures VECM
```
Spec: variables log(WTI spot), crack_321 level; lag order by AIC/SIC over p=1..4; constant in the cointegration space; estimate on post-break sample, show full-sample beside it. Refit monthly; break test annually and forced when rolling 12m OOS RMSE ratio vs RW > 1.05. Page benchmark text: the qualitative Murat & Tokat results (exact RMSE/Theil not in open sources — label "qualitative benchmark").
- Tests: Johansen on a simulated cointegrated pair with β=0.16 → rank 1, β±0.03; break test on a simulated mean shift at obs 120 → within ±3; on a pure random walk the VECM does **not** beat RW (DM p>0.1) — the look-ahead guard.
- DoD: [ ] pipeline, [ ] April-2003 recovery test, [ ] model card fields per conventions, [ ] `pipelines/derived/vecm_refit.py` monthly entrypoint.

### Session C — error-correction signal + page
```python
def ect_signal(vecm, df, z_entry=1.5, z_exit=0.5) -> DataFrame   # ect = beta'y; z on 60m rolling; position = -sign(z) beyond entry, flat inside exit; scaled by |alpha_crude| normalised and by 1/σ (Spec 22 realised vol); only in the direction of 3m crack momentum
```
Backtest through Spec 21's engine; fractionate by turnaround months (Mar–Apr, Sep–Oct).
Theme additions: `cointegration_residual_chart` (fitted relation + ECT with entry bands), `irf_chart`, `model_monitor_chart` (rolling OOS RMSE ratio, DM stat, break status, last refit).
Visualisation spec: crack board table with sparklines; crack forward strip vs 1y ago; seasonal heatmap; cointegration/ECT chart; IRF (crude response to crack shock, 24m); model monitor.
- DoD: [ ] signal never uses y_{t+1} (shift test), [ ] backtest card, [ ] page live.

## Definition of Done (spec)
- [ ] Boards, VECM, ECT signal, page 20 live; monthly refit entrypoint registered in Spec 13's orchestration. [ ] Index + CHANGELOG.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/20_refining-crack-vecm.md. Plan Session A: `core/cracks.py` boards, derived crack series via `pipelines/derived/cracks.py`, tests. Confirm the Spec 10 FRED spot series IDs in the lake first.
