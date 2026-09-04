# pipelines/manual_physical — notes

## Scope: Spec 18's own 4 series only — Spec 19 owns the rest

Per `specs/18_curve-market-structure.md`'s own Data table ("`pipelines/manual_physical/`
(Spec 19 owns; stub reader here)") and `specs/19_fundamentals-physical.md`'s own much larger
scope (EIA STEO/IEA OMR spare capacity, Dubai/Oman/WCS/Maya/Urals diffs, Saudi OSPs,
benchmark-health counts) — this session's `reader.py` reads only the 4 series Spec 18
itself needs for physical-differential bands: `manual.platts.dated_brent`,
`manual.platts.dfl_m1`, `manual.argus.wti_midland_diff`, `manual.argus.wti_houston_diff`.
Spec 19 extends `SERIES_IDS`/`_GEO_BY_SERIES` (or replaces this reader entirely) for its own
much wider set — don't add series here speculatively ahead of that session.

## Not registered in `infra/run_scheduled.py`

Same deferral as `pipelines/futures/`'s `ManualCSVClient`: no real Platts/Argus drop exists
yet (both are paid, no-API commercial licences — hand-dropped CSVs only, matching this
project's own manual-source precedent). `main()` degrades cleanly to a no-op print when
`data/manual/physical/` is empty, exactly like `ManualCSVClient` does — so it is safe to
register once a real drop process exists, but nothing calls it yet.

## Verified (Session C)

`read_physical_csvs()`/`physical_to_ts_long()` tested against a small synthetic fixture
only (`tests/test_manual_physical.py`) — no real Platts/Argus data exists yet.
`core.curve.physical_bands()` itself is tested independently against a synthetic `diff`
series, not gated on this reader ever having real data.
