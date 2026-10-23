# Spec 20 — Refining Economics & Crack Spread Forecasting

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Murat & Tokat (2009) *Energy Economics* 31:85–90 — VECM of WTI spot on 3:2:1 crack spread futures; structural break **April 2003** (not September — a correction on record); unidirectional Granger causality crack → spot; both futures VECMs beat the random walk; crack model "almost as good as" crude futures. Newman (crack mechanics). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Crack boards (superseding the deferred IBKR-based Spec 07 for crude/product cracks — Spec 07 remains for anything IBKR-only) plus a monitored VECM pipeline with an error-correction trading signal. Page `20_cracks.py`.

## Data
Spec 18 unadjusted nearby for cl, rb, ho, g, lco. Spec 10: `fred.dcoilwtico` (WTI spot), `fred.dcoilbrenteu`. Manual: Singapore GO/jet/380 (`pipelines/manual_physical/`). Monthly aggregation = last business day (paper is monthly).

### Session A reality check — the futures legs do not exist (2026-09-05)
Confirmed live against the lake, not assumed: **there are zero `fut.*` rows and zero `fut.*` series IDs**. Spec 18's pipeline is built but has never ingested a real settlement (no IBKR Gateway, no manual CSV — see `pipelines/futures/NOTES.md`). So Session A's boards are built on **spot** legs from Spec 10's FRED pipeline instead, and the board's `m1`/`m2`/`m6` tenor columns read `NaN` ("no data isn't zero") until Spec 18 gets real data.

Three spot product legs were missing from `pipelines/macro/fred_series.py` and were added this session (IDs probed live against the FRED API before use, per the project's "never guess a series_id" rule):

| Added | Title | History |
|---|---|---|
| `fred.dgasnyh` | Conventional gasoline, NY Harbor, regular | 1986-06-02 → current |
| `fred.dgasusgulf` | Conventional gasoline, US Gulf Coast, regular | 1986-06-02 → current |
| `fred.dhoilnyh` | No. 2 heating oil, NY Harbor | 1986-06-02 → current |

That gives a real spot crack history from **1986**, which *spans* Murat & Tokat's own 1993–2008 sample — so Session B's April-2003 break recovery can be tested on real data, not only synthetic. **But note the deviation:** the paper regresses WTI spot on crack *futures*; a spot-crack VECM is a weaker, different claim and must be labelled as a deviation on the page, never presented as a replication. Revisit once real futures settlements land.

ICE gasoil (`g`) and Singapore GO have no legs in the lake at all, so `crack_gasoil_nwe`/`crack_sg_go` are implemented and unit-tested but not wired into the derived pipeline.

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
- Tests: ~~`crack_321(70, 2.20, 2.40)=28.53±0.01`~~ → **`=25.20±0.01`** (correction on record, like the April-2003 one above); unit conversions; RBOB pre-2006 splice flagged (unleaded → RBOB contract change).
- DoD: [x] boards + derived series, [x] tests, [x] one crack cross-checked against EIA's published 3-2-1.

#### `28.53` was wrong — corrected to `25.20`
`2.20 × 42 = 92.40`, `2.40 × 42 = 100.80`, `(2 × 92.40 + 100.80 − 3 × 70)/3 = 75.60/3 = **25.20**`. Both readings of the 3:2:1 formula — `(2·rb42 + ho42 − 3·cl)/3` and `(2·rb42 + ho42)/3 − cl` — are algebraically identical, and no gallons-per-barrel factor yields 28.53 (it would need 43.47). `tests/test_core_cracks.py` asserts 25.20 and carries this reasoning in its own docstring.

#### Session A verification (2026-09-05)
- **`core/cracks.py`** — `crack_321`, `crack_211`, `crack_rbob`, `crack_ho`, `crack_gasoil_nwe`, `crack_sg_go`, `gal_to_bbl`, `tonne_to_bbl_gasoil`, `rbob_splice_flag`, `crack_board`, `crack_seasonal_heatmap`. Pure; ragged crude/product ends aligned by index intersection (FRED publishes WTI a few days behind the product spots — a real, observed gap, not a hypothetical).
- **Signature deviation, deliberate:** the spec writes `crack_board(as_of)`, which would have to read the lake itself, contradicting `00_TRADING_CONVENTIONS.md`'s "pure analytics modules never touch DuckDB". The board takes its already-loaded panel as an argument instead, matching `core/fundamentals.py::inventory_deviation`.
- **`pipelines/derived/cracks.py`** — wrote **45,476 real rows** across 5 cracks (`us321` 10,103, `us211` 10,103, `gulf321` 5,062, `nyh_gasoline` 10,105, `nyh_distillate` 10,103), series `derived.crack.<name>.spot`. Registered in `infra/run_scheduled.py`'s `weekly_fri` group after `macro` (not `daily` — the legs only refresh on the weekly FRED cadence).
- **Cross-check, DoD box 3:** `derived.crack.us321.spot` compared against a 3:2:1 computed independently from the **EIA API** (`petroleum/pri/spt`: `RWTC`, `EER_EPMRU_PF4_Y35NY_DPG`, `EER_EPD2F_PF4_Y35NY_DPG`) — **60 overlapping days, max absolute difference 0.0**. The EIA pull also confirmed the leg mapping exactly (`EER_EPMRU_PF4_RGC_DPG` = 3.569 on 2026-08-21 = `fred.dgasusgulf`; `EER_EPD2F_PF4_Y35NY_DPG` = 4.376 = `fred.dhoilnyh`).
- **Independent plausibility check:** annual means reproduce well-known refining history without being fitted to it — 2015-19 ≈ \$17–19 (the standard NYH 3:2:1 range), 2020 \$10.60 (COVID demand collapse), 2022 \$41.11 (the post-Ukraine margin blowout), 2024 \$20.79, 2025 \$21.75.
- **RBOB splice:** `rbob_splice_flag` exists and is tested, but today's legs are *conventional gasoline spot*, which is continuous across 2006 — the unleaded→RBOB splice is a futures-contract problem, so the flag matters only once Spec 18's futures legs land. Not applied in the derived pipeline.
- Green: `pytest` full suite passes, `ruff check .` clean, `mypy core pipelines` clean (132 files).

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
- DoD: [x] pipeline, [~] April-2003 recovery test — **not recovered, see below**, [x] model card fields per conventions, [x] `pipelines/derived/vecm_refit.py` monthly entrypoint.

#### Session B verification (2026-09-05)
All three of the spec's own acceptance tests pass on synthetic data: Johansen recovers β = **0.1611** (rank 1) against the 0.16±0.03 target; Bai–Perron recovers the obs-120 mean shift at **exactly 120**; the random-walk guard holds. 20 tests in `tests/test_core_vecm.py`, 9 in `tests/test_derived_vecm_refit.py`. Dependencies added with my approval (root NOTES.md rule 7): `statsmodels>=0.15`, `ruptures>=1.1`, `arch>=8.0` — `arch` supplies the Phillips–Perron test statsmodels lacks, and is also what Spec 22's GARCH engine will need.

#### April 2003 is NOT recovered — the honest result
On the real 1993–2008 monthly sample (n=192, log WTI + spot 3:2:1):

| Method | Break found | Distance from April 2003 |
|---|---|---|
| Bai–Perron, 1 break | **2005-03** | +23 months |
| Andrews sup-F | **2004-08** | +16 months |
| Bai–Perron, 2 breaks | **2003-01** + 2005-08 | −3 months (first break) |

With a single break the 2004–05 crude run-up dominates (annual mean log WTI 3.43 → 4.04, crack 5.87 → 12.75), so the search latches onto that far larger level shift. Allowing a second break surfaces **January 2003**, three months before the paper's date — consistent with the same episode, but this is *partial* recovery obtained by relaxing the break count, not a clean replication. Recorded as a miss, per the conventions' "a miss is a visible diagnostic, never a silent pass".

#### The bigger finding: the spot crack is not I(1), so the framework does not transfer
Unit-root tests across every sample, run live:

| Sample | log WTI | spot crack 3:2:1 | Johansen rank |
|---|---|---|---|
| Full 1986–2026 (n=483) | I(1) ✓ (ADF p=0.398, PP p=0.357) | **not I(1)** — ADF p=0.753 but **PP p=0.008** | 2 |
| Paper 1993–2008 (n=192) | I(1) ✓ (ADF p=0.815, PP p=0.652) | **not I(1)** — ADF p=0.342 but **PP p=0.000** | **1** |
| Post-break 2011–2026 (n=188) | I(1) ✓ | **not I(1)** — PP p=0.025 | 2 |

ADF and PP disagree on the crack in every window, and PP — the more powerful test against a persistent-but-mean-reverting series — rejects the unit root decisively. That is exactly what economics predicts of a **refining margin**: it cannot drift without bound, so it mean-reverts. Murat & Tokat's crack *futures* price behaves differently from a spot margin. A Johansen rank of 2 in a two-variable system is the standard signal that the system is already stationary and the cointegration framework does not apply.

The out-of-sample result follows directly: **Theil U = 1.0725** (the VECM is 7% *worse* than a random walk), DM stat +1.81 / p = 0.070 — significantly worse at 10% — with 32 exceptions in 60 forecasts. `oos_status = fail`, `refit_triggered = True`. Granger also runs the *opposite* way to the paper: crack→spot p = 0.442 (no causality), spot→crack p = 0.038.

**Consequence for Session C:** the ECT signal is specified on a cointegrating relationship that does not hold on spot legs. Session C should either wait for real futures settlements (Spec 18) or ship with this failure displayed on the model-monitor card, not hidden. Do not tune the specification until it passes — the negative result is the finding.

#### Session B re-run on real crack FUTURES (2026-09-05)
Spec 18's EIA backfill landed real `fut.*` data the same day, so the model was re-estimated on the variable the paper actually uses: the **m1 3:2:1 crack future**, built from `fut.cl.f01` + `fut.ho.f01` + gasoline (`fut.hu.f01` pre-2006, `fut.rb.f01` after), spliced at `RBOB_SPLICE_DATE`. The splice is continuous on real data — 2005-12-30 11.03 → 2006-01-03 12.01, no step. Series: `derived.crack.us321.m1` (4,649 rows), `derived.crack.hu321.m1` (5,512), plus m2 for both.

**Scorecard against the paper's five claims:**

| Murat & Tokat claim | Spot crack | Crack futures | Verdict |
|---|---|---|---|
| WTI spot and the crack are cointegrated | rank 1 (paper window) | **rank 1**, trace 52.84 vs cv 15.49 | **replicates** |
| β on the crack ≈ 0.16 | 0.0219 | **0.1911** (paper window) | **close** |
| Crack is I(1) | no | **no** — ADF p=0.508 but PP p=0.000 | **fails** |
| Unidirectional causality crack → spot | p=0.442 | crack→spot p=0.284; spot→crack p=0.0007 | **fails — runs the other way** |
| VECM beats the random walk | U=1.0725, DM p=0.070 (sig. worse) | U=0.9941 full / 1.0616 paper, DM p=0.73/0.16 | **fails, but no longer significantly worse** |
| Structural break April 2003 | 2005-03 | **2005-03** | **not recovered** |

Forecast evaluation by sample, crack futures: full 1986–2024 Theil U **0.9941** (DM −0.34, p=0.732); paper 1993–2008 **1.0616** (DM +1.41, p=0.158); post-break 2011–2024 **1.0470** (DM +1.44, p=0.150).

**What this settles.** The *cointegration structure* replicates well on futures — rank 1 with a strongly significant trace statistic and a β of 0.19 against the paper's 0.16. The *forecasting* claim does not: on futures the VECM moves from significantly worse than a random walk (spot, p=0.070) to statistically indistinguishable from one (p=0.73 on the full sample). That is a real improvement in interpretation, not a win. Two failures survive the better data and are therefore not artefacts of the spot proxy: the crack is not I(1) under ADF+PP, and causality runs spot → crack, not crack → spot.

`pipelines/derived/vecm_refit.py` now prefers crack futures automatically and records which leg it used in the card's `crack_source`. `oos_status` gained a third state — a Theil U of 1.02 is still worse than the random walk, merely inside the refit trigger, so `beats_rw` / `within_tolerance` / `fail` replaced a binary pass/fail that would have read as a win.

**Remaining caveat:** EIA's futures route is discontinued after 2024-04-05, so this model cannot be refit on futures past that date without an IBKR feed.

### Session C — error-correction signal + page
```python
def ect_signal(vecm, df, z_entry=1.5, z_exit=0.5) -> DataFrame   # ect = beta'y; z on 60m rolling; position = -sign(z) beyond entry, flat inside exit; scaled by |alpha_crude| normalised and by 1/σ (Spec 22 realised vol); only in the direction of 3m crack momentum
```
Backtest through Spec 21's engine; fractionate by turnaround months (Mar–Apr, Sep–Oct).
Theme additions: `cointegration_residual_chart` (fitted relation + ECT with entry bands), `irf_chart`, `model_monitor_chart` (rolling OOS RMSE ratio, DM stat, break status, last refit).
Visualisation spec: crack board table with sparklines; crack forward strip vs 1y ago; seasonal heatmap; cointegration/ECT chart; IRF (crude response to crack shock, 24m); model monitor.
- DoD: [x] signal never uses y_{t+1} (shift test), [x] backtest card, [x] page live.

#### Session C verification (2026-09-05)
`core/vecm.py` gained `ect_signal`, `backtest_positions` and `irf_table`; `core/theme.py` gained `cointegration_residual_chart`, `irf_chart` and `model_monitor_chart`; page `apps/dashboard/pages/20_cracks.py` is live with five tabs. 16 new tests in `tests/test_core_vecm_signal.py`.

**The shift test caught a real look-ahead bug in the signal itself.** On its first run `ect`, `z`, `raw_position` and `momentum` all matched between a truncated and a full sample, but `position` did not: `vol_scale` was being normalised by the **full-sample median**, which reads observations after *t* into every earlier position. Fixed to an expanding median. This is exactly the failure the DoD box exists to catch, and it would have silently inflated any backtest.

**Two stand-ins, both surfaced in the UI rather than buried:**
- *Backtest engine.* The spec says "backtest through Spec 21's engine", but `core/systematic.py` does not exist. `backtest_positions` is a minimal position × forward-move calculation with turnaround fractionation — no costs, slippage or position limits. Replace when Spec 21 lands.
- *Volatility scaling.* The spec says "1/σ (Spec 22 realised vol)", but `core/risk.py` does not exist. A plain rolling standard deviation stands in for GARCH-MIDAS-EVT.

**Page honesty, per the runbook's "render NO-DATA, never fabricate":** the board's m1/m2/m6 tenors render empty because no *current* futures exist (EIA's route ends 2024-04-05 and no IBKR feed is connected) — a two-year-old settlement shown as a live tenor would be worse than a blank. The forward strip is labelled with its own as-of date and an explicit "not current" warning. The model card renders the random-walk failure as an `st.error`.

Crack futures were extended to m3/m4 (EIA publishes ranks 1–4) so the forward strip has real shape; there is still no m6 from this source.

## Definition of Done (spec)
- [x] Boards, VECM, ECT signal, page 20 live; monthly refit entrypoint registered in Spec 13's orchestration. [x] Index + CHANGELOG.

**Spec 20 is complete, with the model's failure displayed rather than hidden.** Carry forward into Specs 21/22: `backtest_positions` and the rolling-σ vol scaling in `core/vecm.py` are stand-ins to be replaced by the real systematic and risk engines, and page 20's backtest card should be re-pointed at them.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/20_refining-crack-vecm.md. Plan Session A: `core/cracks.py` boards, derived crack series via `pipelines/derived/cracks.py`, tests. Confirm the Spec 10 FRED spot series IDs in the lake first.
