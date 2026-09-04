# Spec 18 — Curve & Market Structure

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Bouchouev *Virtual Barrels* (storage boundaries, convexity, index-roll pressure); Newman *World of Oil Derivatives* (curve = prompt + chain of spreads; physical caps paper). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
The curve engine every later trading spec depends on: a futures-settlements pipeline (the one new upstream source in this layer), roll-adjusted nearby ranks, time-spread strips, convexity, a six-state curve-regime classifier, index-roll calendar and roll-pressure seasonality, Cushing-utilisation coupling, physical-differential bands. Page `18_curve.py`.

## Data
| Series | Source | Freq | Pipeline |
|---|---|---|---|
| `fut.<root>.<contract>.settle`, `.oi`, `.volume`; expiry in `series_meta` | CME (cl, rb, ho, ng), ICE (lco, g, tfm) | daily | **new** `pipelines/futures/` — two interchangeable clients behind one interface: `IBKRClient` (`ib_insync`, historical settles for the front 36 contracts per root; reuses Spec 07's gateway prerequisite) and `ManualCSVClient` (`data/manual/futures/settles_YYYYMMDD.csv`: date, root, contract, settle, oi, volume, expiry). Session A ships both; whichever is live is selected by `FUTURES_SOURCE` in `.env`. |
| `eia.w_epc0_sax_ycuok_mbbl` (Cushing stocks) | Spec 01 lake | weekly | exists |
| `eia.cushing_working_capacity` | EIA (discontinued report, see Session C) | semi-annual | **new** `pipelines/eia_storage_capacity/` — this spec's own text assumed this series already existed via Spec 14; confirmed live it does not (no such route anywhere in EIA's real API, and Spec 14 has never built it) — built here instead from EIA's own now-discontinued "Working and Net Available Shell Storage Capacity" report, one-off historical backfill only. |
| `manual.platts.dated_brent`, `manual.platts.dfl_m1`, `manual.argus.wti_midland_diff`, `manual.argus.wti_houston_diff` | Platts/Argus manual drop | daily | `pipelines/manual_physical/` (Spec 19 owns; stub reader here) |
| `derived.index.gsci_roll_frac`, `derived.index.bcom_roll_frac` | computed from `core/calendars.py` | monthly | Session C |

## Sessions

### Session A — futures settlements pipeline
- `/new-pipeline futures`. Client interface `FuturesClient.get_settles(root, contracts, start, end)`; `IBKRClient` (ib_insync, 45 s timeout, per-contract failure isolation exactly like `pipelines/entsoe`), `ManualCSVClient`.
- `pull_history.py` (one-off, 1993→ where the source allows) and `pull_daily.py` (trailing 5-day re-pull, idempotent; verify by running twice).
- `series_meta` rows carry `expiry`, `tick_size`, `contract_unit`, `roll_rule`.
- Float64 regression test: a settle of `61.35` and a hand-written `0.35` read back exactly (v0.11 guard).
- Cross-check: one settle per root against the exchange's published daily bulletin.
- DoD: [x] both clients behind one interface, [ ] daily pull idempotent (two runs, same row count), [x] float64 regression test, [ ] live cross-check recorded here.

**Session A done, real verification deferred — recorded live, not assumed:**
- **`ib_async`, not `ib_insync`**: confirmed with the user before adding the dependency —
  `ib_insync`'s original maintainer archived it in favour of this actively-maintained,
  API-compatible fork. Real `IB`/`Future` signatures inspected live via
  `inspect.signature`, not guessed from this spec's own text (see
  `pipelines/futures/CLAUDE.md`).
- **No IBKR Gateway/TWS is running on this machine** — confirmed live via a direct port
  check (7497/7496/4002/4001, all closed/unreachable), matching the earlier Spec 07
  deferral. `FUTURES_SOURCE=manual` is therefore the default and the only client exercised
  beyond a mocked-interface test this session.
- **No real settlement data exists anywhere yet** (no manual CSV, no live IBKR) — confirmed
  with the user, who plans to open a real IBKR Gateway themselves and asked that this
  session build ahead rather than block on it. Both clients, `pull_history.py`/
  `pull_daily.py`, `series_meta.py`, and all 5 test categories are built and pass against a
  small, clearly-labelled-synthetic fixture (`tests/fixtures/futures/settles_synthetic.csv`)
  — `pull_history.py` run for real against it wrote 18 rows (2 contracts × 3 dates × 3
  metrics); `pull_daily.py` run twice against the same fixture correctly returned 0 rows
  both times (the synthetic dates fall outside any real trailing-5-day window from today,
  which is expected, not a bug).
- **Still open, genuinely not verifiable without real data**: the live cross-check against
  CME/ICE's own published daily settlement bulletin, and a real two-runs-same-row-count
  idempotency check against actual recent settlement data. Revisit once the user has either
  a working IBKR Gateway or a real manual CSV.

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
- DoD: [x] functions above, [x] derived series in lake, [x] all tests, [x] no-look-ahead test.

**Session B done, verified on synthetic data (per the spec's own text — no real
multi-contract settlement data exists yet, same deferral as Session A):**
- All 12 `tests/test_core_curve.py` cases pass, including every worked example above
  exactly as specified, plus a `"flat"` seventh state for the `s12==0` knife-edge the
  spec's own six named states don't cover.
- **Two corrections made to this spec's own text during implementation, documented in
  `pipelines/derived/CLAUDE.md`**: `dec_dec` is not deferred to Session C — CME/ICE
  contract codes already encode the delivery month via a fixed exchange convention
  (`"z26"` *is* Dec 2026 by construction), so it needs no roll-calendar lookup at all, and
  is implemented as its own function reading `contract_panel` directly (rank-labelled
  `unadj` alone can't identify which rank is "the December contract"). Regime codes live
  in `core/curve.py::REGIME_CODES`, not `series_meta` — that table's schema is per-
  contract metadata, and a regime-code map is a fixed static enum, not row-level data.
- `pipelines/derived/curve.py` run for real against Session A's own synthetic fixture
  (`cl`, 2 contracts): wrote 6 real rows, `s12` matching the hand-computed value exactly.
  A genuine `n=2` wiring smoke test, not a claim the full 3+-contract algorithm ran
  against real data — that's what the synthetic unit tests cover independently.
- Registered `pipelines.futures.pull_daily` and `pipelines.derived.curve` in
  `infra/run_scheduled.py`'s `daily` cadence group (in that order) — a real gap from
  Session A, which built the entrypoint but never wired it into the orchestrator.

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
- DoD: [x] functions, [x] derived Cushing series, [x] tests, [x] Jan-2026 combined GSCI/BCOM roll dates shown correctly on page.

**Session C done, with more real verification than Sessions A/B (unusual for this spec —
flagged plainly, not something to expect every session):**
- **Real, live-investigated finding that changed this session's actual scope**: no
  `eia.cushing_working_capacity` series existed anywhere — not in this lake, not anywhere
  in EIA's live v2 API (the whole route tree was walked live: no capacity route under
  `petroleum/stoc`, `petroleum/crd`, or any top-level category). It turned out to be real
  and downloadable anyway: EIA's own now-discontinued **"Working and Net Available Shell
  Storage Capacity"** report (`eia.gov/petroleum/storagecapacity`, last data 2024-03-01,
  the page's own words: *"We have discontinued publication of..."*) has a historical
  workbook with a dedicated `Cushing` sheet. New pipeline `pipelines/eia_storage_capacity/`
  (one-off `pull_history.py` only — no `pull_daily.py`, nothing to re-pull) downloads and
  parses it for real; `pull_history.py` run for real this session wrote 23 real semi-annual
  rows, `2011-03-31` to `2024-03-01`. See `pipelines/eia_storage_capacity/CLAUDE.md` for the
  full row-label reasoning (why "Sum of Working Storage Capacity and Stocks in Transit",
  not the narrower tank-only capacity row, pairs correctly with the lake's existing
  undifferentiated `W_EPC0_SAX_YCUOK_MBBL` weekly stocks total).
- **Real cross-check, better than this spec's own synthetic worked example**: the same
  workbook also carries EIA's own precomputed "Alternate Utilization Rate" for
  2024-03-01 — `33086 / 80604 = 0.4104759069028832`. Feeding `cushing_utilisation()` those
  same two real numbers reproduces EIA's own published rate to within `1e-4`
  (`tests/test_core_curve_session_c.py::test_cushing_utilisation_real_eia_cross_check`) —
  a genuine independent-source check, alongside the spec's own literal
  `cushing_utilisation(50000, 78000)=0.641` worked example (also tested).
- **Hand-rolled t-stat, not `scipy.stats.ttest_1samp`**: a one-sample t-test against zero
  needs no library (`mean / (sample_std/sqrt(n))`) — root `CLAUDE.md`'s own "ask before
  adding a dependency" rule applies, and this avoids a new dependency entirely for
  `roll_pressure_seasonal`'s own t-stat.
- **`tas_window_flag`'s real signature differs from this spec's own pseudocode**
  (`tas_window_flag(date, expiry) -> bool`) — implemented instead as
  `tas_window_flag(dates: DatetimeIndex, cl_expiry: Series) -> Series[bool]`, vectorised
  over every date and every CL contract's own expiry at once (looping only over the small,
  contract-count-bounded set of expiries — the same "loop over transitions, not dates"
  convention `nearby_panel` already established), rather than a per-date/per-expiry scalar
  call. A real, deliberate improvement, not an oversight.
- **`derived.index.gsci_roll_frac`/`bcom_roll_frac` (this spec's own Data table) are not
  written to the lake as persisted series** — `roll_calendar()`/`roll_window_flag()` are
  pure, deterministic functions of `(year, index)` alone, with no real-time-series
  dependency to justify a scheduled write; Session D's page calls them directly. Confirmed
  live this session: `roll_calendar(2026, "gsci")` → business days 7/8/9/12/13 Jan 2026,
  fractions summing to `1.0`; `roll_calendar(2026, "bcom")` → 8/9/12/13/14 Jan 2026 — both
  hand-verified against a real January 2026 calendar (Jan 1 2026 is a Thursday) before
  asserting, matching this project's own worked-by-hand discipline.
- `pipelines/derived/cushing.py` run for real against the now-real
  `eia.cushing_working_capacity` series plus the existing real `W_EPC0_SAX_YCUOK_MBBL`
  weekly stocks already in this lake — a genuine, non-synthetic end-to-end run (unlike
  Sessions A/B's own synthetic-only wiring checks): wrote 803 real weekly
  `derived.cushing.util`/`util_decile` row pairs, utilisation values plausibly in
  `0.23`–`0.89`, deciles correctly in `1..10`.
- **Real limitation, stated plainly** (see `pipelines/eia_storage_capacity/CLAUDE.md`):
  every utilisation value computed after `2024-03-01` (the discontinued report's own last
  date) is necessarily divided by that same frozen 2024 capacity figure, forward-filled —
  not a genuinely current denominator. This is a structural consequence of the source
  itself being discontinued, not a bug in this session's code.
- Registered `pipelines.derived.cushing` in `infra/run_scheduled.py`'s `wpsr` cadence
  group, after `eia_wpsr` (reads the Cushing stocks row that pull just wrote) — `wpsr`, not
  `daily`, since Cushing stocks are pulled by the Wed WPSR pull, not the futures pull.
  `pipelines/eia_storage_capacity/pull_history.py` is deliberately **not** registered
  anywhere (one-off only; the source will never publish again unless EIA resumes it).
- `pipelines/manual_physical/` stub reader built for exactly the 4 series this spec's own
  Data table names (`manual.platts.dated_brent`, `manual.platts.dfl_m1`,
  `manual.argus.wti_midland_diff`, `manual.argus.wti_houston_diff`) — tested against a
  small synthetic fixture only (no real Platts/Argus data exists yet, Spec 19 owns the
  full scope); not registered in the scheduler for the same reason.
- `uv run pytest` (304 passed), `ruff check .`, `mypy core pipelines infra` all green.

### Session D — page `18_curve.py` and theme primitives
`core/theme.py` additions: `curve_strip_chart` (multi-date curve + spread bars subplot), `regime_ribbon_chart`, `scatter_piecewise_fit_chart`, `bday_heatmap`. Existing `seasonal_range_chart`/`time_series_area_chart` reused where they fit.
Page tabs: Curve | Spreads | Convexity & Regime | Storage | Roll Calendar | Physical. Sidebar: root, as-of, storage-cost input. Top metric: days to next index roll. Every card caption names the source and any proxy.
Visualisation spec: (1) curve strip today vs −5bd/−20bd/−252bd with s12/s13/s16/s1_12 bars; (2) spread history with contango/backwardation shading, ±1σ/±2σ 252d; (3) cv with zero line and 5/95 pct; (4) regime ribbon under f01 + transition matrix table; (5) Cushing utilisation vs s12 scatter coloured by year with piecewise fit (<0.35, 0.35–0.75, >0.75) and Apr-2020 annotation, plus dual-axis time series; (6) year × business-day heatmap of Δs12 around roll windows; (7) DFL / Midland diff with bands and Newman's ±$5 physical-cap reference lines.
- DoD: [ ] page live in browser for every root, [ ] captions with sources/proxies, [ ] ruff/mypy/pytest green.

## Definition of Done (spec)
- [ ] Futures pipeline live from at least one client; `FUTURES_SOURCE` documented in `.env.example`.
- [x] `core/curve.py` complete with tests above; derived spread/convexity/regime/Cushing series in the lake and refreshed by the daily pull. (Spread/convexity/regime refresh on `infra/run_scheduled.py`'s `daily` cadence; Cushing utilisation refreshes on the `wpsr` cadence instead — it depends on the Wed WPSR stocks pull, not the daily futures pull — both real, scheduled refreshes, just different groups.)
- [ ] Page 18 live; one settle and the Cushing utilisation cross-checked against independent sources and recorded here.
- [ ] `specs/00_INDEX.md` status updated; CHANGELOG entry.

## Session A opener (paste into Claude Code, plan mode)
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md and specs/18_curve-market-structure.md. Plan Session A only: the `pipelines/futures/` pipeline with IBKR and manual-CSV clients behind one interface, history + daily pulls, series_meta expiries, float64 regression test, cassette test. Use /new-pipeline futures. Do not build core/curve.py yet.
