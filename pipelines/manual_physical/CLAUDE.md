# pipelines/manual_physical — Claude Code Guide

## Real, known future-merge consideration — read before touching this file again

Spec 18's own Session D (on the still-open, unmerged `feat/futures-settlements`
branch) already built a small `pipelines/manual_physical/` stub scoped to exactly the
4 series that spec's own Data table names (`manual.platts.dated_brent`,
`manual.platts.dfl_m1`, `manual.argus.wti_midland_diff`,
`manual.argus.wti_houston_diff`), with a note in its own CLAUDE.md: *"Spec 19 owns the
full scope."* This session (Spec 19 Session B, on `feat/fundamentals-physical`, based
off `main`) built this package **independently and from scratch**, since that other
branch's work is invisible here until its own PR merges — this file's `SERIES_META`
does **not** include Spec 18's own 4 series names.

**Whichever PR merges to `main` second will hit a real merge conflict on this exact
package** (two independently-written `reader.py` files, same path, genuinely
different scope) — resolve it by taking this session's own broader `SERIES_META`
dict and adding Spec 18's own 4 series into it (same shape: unit/geo/freq per
series_id), not by picking one file over the other wholesale. Don't let this note go
stale — update it once one of the two PRs actually merges.

## Scope: Spec 19's own Data section, verbatim

17 series: two agencies' own spare-capacity estimates (kept separate, never averaged
— see `core.fundamentals.spare_capacity`'s own "never average silently" instruction),
Dubai M1/M3 + Oman + Brent-Dubai EFS + WCS/LLS/Maya/Mars/Urals differentials, 3 Saudi
Aramco OSPs (Arab Light to Asia/NWE/US), and 3 benchmark-health counts (Dated Brent
window trades, Dubai partials, WTI Midland's own share of BFOET). No real data exists
for any of these yet (all are paid, no-API commercial licences — Platts/Argus/DME/EIA
STEO/IEA OMR/Saudi Aramco all require a hand-dropped CSV, matching this project's own
long-standing manual-source precedent, e.g. `pipelines/opec_momr/quotas.csv`).

## Not registered in `infra/run_scheduled.py`

Same deferral as every other manual-only source in this project (no real drop process
exists yet). `main()` degrades cleanly to a no-op print when
`data/manual/physical/` is empty.

## Verified (Spec 19 Session B)

`read_physical_csvs()`/`physical_to_ts_long()` tested against a small synthetic
fixture only (`tests/test_manual_physical.py`) — no real Platts/Argus/Aramco data
exists yet. Every `core.fundamentals` function this pipeline's own data would feed
(`quality_spreads`, `refining_constraint_index`, `benchmark_health`, `osp_signal`) is
tested independently against synthetic data, not gated on this reader ever having
real data.
