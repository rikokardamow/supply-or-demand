# pipelines/manual_physical — notes

## Resolved: the two-branch collision on this package (was a warning, now a record)

Specs 18 and 19 each built this package independently, on separate branches, without
sight of the other — Spec 18 a 4-series stub (its own Data table: "`pipelines/
manual_physical/` (Spec 19 owns; stub reader here)"), Spec 19 the full 17-series scope.
Both PRs reached `main` with two different `reader.py` files at this same path.

**How it was actually resolved**: PR #42 (Spec 18) merged first; PR #43 (Spec 19) merged
second and resolved the conflict by keeping Spec 19's `SERIES_META` dict — which carries
`(unit, geo, freq)` per series, because these series genuinely differ on all three — and
folding Spec 18's own 4 series into it as `USD/bbl` / `D` entries. Neither file was taken
wholesale, and Spec 18's `SERIES_IDS`/`_GEO_BY_SERIES` pair is gone: `SERIES_IDS` is now
derived from `SERIES_META`, and geo lives in that same dict. `tests/test_manual_physical.py`
is likewise the union of both branches' cases, with one test asserting specifically that
Spec 18's 4 series survived the merge.

**21 series total.** Don't re-split this package per spec — a later spec that needs a new
manual physical series adds it to `SERIES_META`.

## Scope

Spec 19's own Data section: two agencies' spare-capacity estimates (kept separate, never
averaged — see `core.fundamentals.spare_capacity`'s own "never average silently"
instruction), Dubai M1/M3 + Oman + Brent-Dubai EFS + WCS/LLS/Maya/Mars/Urals
differentials, 3 Saudi Aramco OSPs (Arab Light to Asia/NWE/US), and 3 benchmark-health
counts (Dated Brent window trades, Dubai partials, WTI Midland's own share of BFOET).
Plus Spec 18's 4: `manual.platts.dated_brent`, `manual.platts.dfl_m1`,
`manual.argus.wti_midland_diff`, `manual.argus.wti_houston_diff`.

No real data exists for any of these yet (all are paid, no-API commercial licences —
Platts/Argus/DME/EIA STEO/IEA OMR/Saudi Aramco all require a hand-dropped CSV, matching
this project's own long-standing manual-source precedent, e.g.
`pipelines/opec_momr/quotas.csv`).

## Not registered in `infra/run_scheduled.py`

Same deferral as every other manual-only source in this project (no real drop process
exists yet). `main()` degrades cleanly to a no-op print when `data/manual/physical/` is
empty — safe to register once a real drop process exists, but nothing calls it yet.

## Verified

`read_physical_csvs()`/`physical_to_ts_long()` tested against a small synthetic fixture
only (`tests/test_manual_physical.py`) — no real Platts/Argus/Aramco data exists yet.
Every downstream function this pipeline's data would feed is tested independently against
synthetic data, not gated on this reader ever having real data: `core.fundamentals`'s
`quality_spreads`, `refining_constraint_index`, `benchmark_health`, `osp_signal` (Spec 19)
and `core.curve.physical_bands` (Spec 18).
