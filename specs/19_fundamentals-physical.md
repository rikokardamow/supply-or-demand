# Spec 19 — Fundamentals & Physical Market

**Sources:** Imsirovic (benchmarks, spare capacity, market power, OSPs); Carollo *Understanding Oil Prices* (classical vs modern S&D, refining quality mismatch, stock-change scatter failure, analysts' vicious circle); Spurga; *New Era of Oil Trading*. Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
The regime-context and guardrail layer — conditioning variables for Spec 21, not direct signals. Almost entirely analytics over data Specs 01/06/10/14 already ingest, plus manual physical-market drops. Page `19_fundamentals.py`.

## Data (existing unless marked)
Spec 01: US crude/product stocks, PADD stocks, production, refinery inputs, utilisation. Spec 06: MOMR (demand, non-DoC supply, OECD stocks, oil-on-water, DoC production by country, quotas), JODI, Baker Hughes rigs. Spec 10: WTI, Brent, HH. Spec 14: CFTC COT (managed-money, producer/merchant, OI for cl/lco/rb/ho), Cushing capacity. Spec 18: spreads, Cushing utilisation.
**New manual drops** (`pipelines/manual_physical/`, `data/manual/physical/`): EIA STEO + IEA OMR spare capacity (two agencies, both kept); Dubai M1/M3, Oman, Brent–Dubai EFS, WCS, Maya, Mars, Urals diffs; Saudi OSPs (Arab Light to Asia/NWE/US); benchmark-health counts (Dated Brent window trades, Dubai partials, WTI Midland share of BFOET). Any missing series renders its card in a visible "NO DATA — manual drop required" state, never an exception.

## Sessions

### Session A — `core/fundamentals.py` inventory, cover, spare capacity, positioning
```python
def inventory_deviation(series, years=5, exclude=(2020,)) -> DataFrame   # thin wrapper over core.seasonal.seasonal_stats: value, mean, min, max, dev, dev_z (ISO-week seasonal)
def days_of_cover(stocks_kbbl, refinery_inputs_kbd) -> Series              # stocks/(inputs*7)
def spare_capacity(eia, iea) -> DataFrame                                   # eia, iea, avg, disagreement — table shows both, chart never averages silently
def spare_cap_regime(spare, thresholds=(2.0, 4.0)) -> Series               # 'tight' < 2 mb/d, 'balanced', 'ample' > 4
def cot_percentiles(long, short, oi, window=156) -> DataFrame              # net, net_pct_oi, pct_rank_3y, z
```
Write `derived.inv.dev_z.uscrude`, `derived.spare_cap.regime`, `derived.cot.<root>.mm_pct_3y` to the lake.
- Tests: 2020 absent from the 2026 band; `days_of_cover(420000, 16000)=26.25`; pct_rank ∈ [0,1]; `spare_cap_regime(1.5)='tight'`, `(3.0)='balanced'`, `(4.5)='ample'`.
- DoD: [ ] functions + derived series, [ ] tests, [ ] cross-check one COT net-length figure against the CFTC report PDF.

### Session B — quality mismatch, Carollo diagnostic, shale response, benchmark health, OSP
```python
def quality_spreads(prices) -> DataFrame           # brent_dubai_efs, wti_wcs, lls_maya, brent_urals, sweet_sour_index (mean z)
def refining_constraint_index(utilisation, complex_simple_margin_spread, light_heavy) -> Series   # Carollo's binding-constraint gauge
def carollo_scatter(delta_stocks_q, delta_brent_q) -> dict   # OLS slope, R², share_wrong_sign (expect ≈0.5)
def shale_response(rigs, wti_f12, lags=(13, 26)) -> DataFrame   # rolling OLS Δrigs ~ ΔWTI12m lagged; beta, t
def benchmark_health(window_trades, partials, midland_share) -> DataFrame   # z-scores, 'thin' flag when window_trades < p10(3y)
def osp_signal(osp_asia, dubai_m1_m3) -> DataFrame   # divergence flag: OSP up while Dubai structure weakens
```
- Tests: `carollo_scatter` on zero-relationship synthetic data → share_wrong_sign ∈ [0.4, 0.6]; `shale_response` recovers an injected beta within ±20%; benchmark 'thin' flag only below p10.
- DoD: [ ] functions, [ ] manual_physical pipeline + reader test, [ ] tests.

### Session C — page `19_fundamentals.py`
Theme additions: `grouped_agency_bars` (three-agency S&D), `dual_axis_inverted_chart` (spare cap inverted vs price with regime shading), `sign_agreement_scatter`.
Visualisation spec: (1) S&D balance bars (IEA/EIA/OPEC side by side) + call-on-OPEC line, caption stating agency disagreement in mb/d; (2) spare capacity (inverted) vs Brent, 30d realised vol area, tight/balanced/ample shading; (3) inventory bands (reuse `seasonal_range_chart`, ex-2020) + days-of-cover; (4) Carollo scatter annotated with R² and "% of quarters violating the classical model"; (5) light-heavy panel + refining-constraint index + utilisation; (6) rolling shale beta + basin production (Spec 06 DPR if present, else caption); (7) COT net length % OI with 3y percentile bands, producer/merchant short overlay; (8) benchmark-health z-scores with thin flags; (9) OSP vs Dubai M1–M3.
- DoD: [ ] page live, [ ] every card caption contains "Source:", [ ] NO-DATA state verified by temporarily removing a manual file.

## Definition of Done (spec)
- [ ] All Session A/B functions and derived guardrail series in lake. [ ] Page 19 live. [ ] One COT and one inventory figure cross-checked against the publisher. [ ] Index + CHANGELOG.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/19_fundamentals-physical.md. Plan Session A: `core/fundamentals.py` (inventory_deviation over core.seasonal, days_of_cover, spare_capacity, spare_cap_regime, cot_percentiles), derived series written by a `pipelines/derived/fundamentals.py` step, tests. Confirm which Spec 14 CFTC series IDs exist in the lake before coding; do not guess.
