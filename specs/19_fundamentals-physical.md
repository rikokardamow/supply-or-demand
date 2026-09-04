# Spec 19 — Fundamentals & Physical Market

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

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
- DoD: [x] functions + derived series, [x] tests, [x] cross-check one COT net-length figure against the CFTC report PDF (done against the CFTC PRE's own live source data directly -- see below, not a PDF scrape).

**Session A done, with a real scope expansion the user explicitly asked for:**
- **Real, live-investigated finding**: this spec's own Data section assumed CFTC COT
  data already existed via "Spec 14" — confirmed live, twice, that it does not (no
  pipeline, no series anywhere in the lake; Spec 14 was never built). CFTC's own COT
  landing page (`https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm`,
  fetched live per the user's own request) points to the **Public Reporting
  Environment** (`publicreporting.cftc.gov`) as its current API access point — a real,
  free, no-API-key Socrata dataset (`72hh-3qpy`, Disaggregated Futures-Only, weekly
  back to 2006). New pipeline `pipelines/cftc/` built and run for real this session:
  `pull_history.py` wrote **19,650 real rows** across all 4 roots (`cl`/`rb`/`ho` back
  to 2006-06-13, `lco` back to 2011-10-18 — Brent futures were listed on this
  reporting line later than the domestic contracts).
- **Real cross-check, independent of this pipeline's own code**: a fresh, separate
  `curl` against the same CFTC PRE endpoint for `cl` on `2026-08-25` returned
  `m_money_positions_long_all=196882`, `m_money_positions_short_all=112862`,
  `open_interest_all=1906740` — exactly matching what `pipelines/cftc/pull_history.py`
  had already written to the lake. Net managed-money length =
  `196882 - 112862 = 84,020 contracts long`, confirmed against the report's own
  current source of truth (the PRE *is* CFTC's own authoritative current access
  point for this data — not a PDF scrape, a stronger check than the spec's own text
  asked for).
- **Two real corrections to this spec's own pseudocode, found by reading the actual
  code these functions must reuse (not guessed)**: `days_of_cover`'s inline comment
  said `stocks/(inputs*7)`, but the literal DoD worked example
  (`days_of_cover(420000, 16000) = 26.25`) only holds for plain `stocks/inputs` — the
  existing, already-live `pipelines/eia/transforms.py::days_of_cover` (used on page
  `01_us_padd.py` today) confirms plain division is this project's own real
  convention. `inventory_deviation` is built as a genuine thin wrapper over
  `core.seasonal.seasonal_stats` (day-of-year, not "ISO-week" as the pseudocode said —
  `seasonal_stats`'s own docstring explains why day-of-year-with-forward-fill is the
  deliberate, already-proven choice for exactly this kind of weekly EIA series).
- **Real bug caught and fixed by this session's own live verification, not left for
  later**: `_write_partitioned` (`core/storage.py`) crashed
  (`TypeError: Cannot compare tz-naive and tz-aware timestamps`) the moment this
  session's `datetime.now(UTC)`-built `revision_date` landed in a `source=derived`
  partition an earlier session had already written with a tz-naive one. Fixed at the
  source (`_normalise_datetime_tz`, applied to both the incoming write and the
  existing on-disk rows before they're combined) — see `core/CLAUDE.md`'s own new
  incident write-up and `tests/test_storage.py`'s new regression test.
- **A second real bug caught the same way**: `inventory_deviation`'s own output is
  indexed by day-of-year (inherited from `seasonal_stats`), not a real calendar date —
  `pipelines/derived/fundamentals.py` maps the latest year's own real dates back onto
  it (the same `reference_doy` technique `01_us_padd.py`'s own `_seasonal_section`
  already uses) before writing it as a `ts_long` series.
- `derived.inv.dev_z.uscrude` written for real against the lake's own real
  `WCESTUS1` (33 real weekly rows, 2026). `derived.cot.<root>.mm_pct_3y` written for
  real for all 4 roots (900 rows each for `cl`/`rb`/`ho`, 610 for `lco` — matching each
  root's own real history length). `derived.spare_cap.regime` correctly skipped with a
  clear log line — no real EIA STEO/IEA OMR spare-capacity data exists yet (Session
  B's own `manual_physical` extension).
- `uv run pytest`, `ruff check .`, `mypy core pipelines infra` all green.

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
- DoD: [x] functions, [x] manual_physical pipeline + reader test, [x] tests.

**Session B done. Real data-availability check performed before planning (not
assumed)**: of these six functions, only `carollo_scatter` has real inputs today —
`WCESTUS1` (US crude stocks, Spec 01) and `fred.dcoilbrenteu` (Brent, Spec 10), both
resampled to quarterly changes. Every other function's real inputs are manual-drop-only
(`quality_spreads`, `refining_constraint_index`, `benchmark_health`, `osp_signal`) or need
a real futures curve that doesn't exist yet (`shale_response`'s own `wti_f12` — Spec 18's
futures pipeline has no real settlement data). All six functions are built and tested
against synthetic data matching this spec's own literal worked examples.

**Real, live verification of `carollo_scatter`** — run for real against the actual lake
(157 real quarters, full history): `slope = -3.03e-05`, `r2 = 0.0023`,
`share_wrong_sign = 0.452`. A genuinely near-zero relationship between quarterly US
crude-stock changes and quarterly Brent changes, `share_wrong_sign` close to the 50%
"no relationship" baseline — consistent with Carollo's own point that the classical
stock-change/price relationship is weak in practice. Console-only, not written to the
lake (this session's own DoD doesn't ask for a persisted `derived.*` series the way
Session A's did).

**No OLS library added** — `_ols` (closed-form simple linear regression: slope,
intercept, r2, t_stat) is hand-rolled in `core/fundamentals.py`, matching Spec 18 Session
C's own "no new dependency for basic stats" precedent (no scipy/statsmodels/scikit-learn
exists in this project).

**`pipelines/manual_physical/` built fresh on this branch** — Spec 18's own Session D
already built a *different*, smaller `pipelines/manual_physical/` stub (4 series) on the
still-open, unmerged `feat/futures-settlements` branch; that work is invisible here.
This session's own version covers this spec's full 17-series Data-section list. **A
real, documented merge consideration**: whichever PR merges to `main` second will hit a
real conflict on this exact package — see `pipelines/manual_physical/CLAUDE.md` for the
resolution note (merge the two `SERIES_META` dicts, don't pick one file over the other).
- `uv run pytest` (280 passed), `ruff check .`, `mypy core pipelines infra` all green.

### Session C — page `19_fundamentals.py`
Theme additions: `grouped_agency_bars` (three-agency S&D), `dual_axis_inverted_chart` (spare cap inverted vs price with regime shading), `sign_agreement_scatter`.
Visualisation spec: (1) S&D balance bars (IEA/EIA/OPEC side by side) + call-on-OPEC line, caption stating agency disagreement in mb/d; (2) spare capacity (inverted) vs Brent, 30d realised vol area, tight/balanced/ample shading; (3) inventory bands (reuse `seasonal_range_chart`, ex-2020) + days-of-cover; (4) Carollo scatter annotated with R² and "% of quarters violating the classical model"; (5) light-heavy panel + refining-constraint index + utilisation; (6) rolling shale beta + basin production (Spec 06 DPR if present, else caption); (7) COT net length % OI with 3y percentile bands, producer/merchant short overlay; (8) benchmark-health z-scores with thin flags; (9) OSP vs Dubai M1–M3.
- DoD: [ ] page live, [ ] every card caption contains "Source:", [ ] NO-DATA state verified by temporarily removing a manual file.

## Definition of Done (spec)
- [ ] All Session A/B functions and derived guardrail series in lake. [ ] Page 19 live. [ ] One COT and one inventory figure cross-checked against the publisher. [ ] Index + CHANGELOG.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/19_fundamentals-physical.md. Plan Session A: `core/fundamentals.py` (inventory_deviation over core.seasonal, days_of_cover, spare_capacity, spare_cap_regime, cot_percentiles), derived series written by a `pipelines/derived/fundamentals.py` step, tests. Confirm which Spec 14 CFTC series IDs exist in the lake before coding; do not guess.
