# pipelines/derived — Claude Code Guide

Thin steps that read the lake, call pure `core/<topic>.py` analytics functions, and write
`derived.*` series back — never the reverse (`core/` modules never touch DuckDB, per root
CLAUDE.md). Modules here: `curve.py` and `cushing.py` (Spec 18 Sessions B/C) and
`fundamentals.py` (Spec 19 Session A) — the two specs were built on separate branches and
landed together, PR #42 then PR #43.
## `fundamentals.py` — `derived.spare_cap.regime` deliberately not written this session

`core.fundamentals.spare_capacity`/`spare_cap_regime` are built and tested (synthetic data
only) — but their only real inputs (EIA STEO + IEA OMR spare-capacity manual drops) don't
exist anywhere yet; that's Session B's own `pipelines/manual_physical/` extension. Rather
than write an empty or fabricated `derived.spare_cap.regime` row, `main()` logs this
plainly and skips the write — same "don't fake it" discipline as every prior session's own
missing-data gap (Spec 18 Sessions A/D).

## Verified (Session A)

`derived.inv.dev_z.uscrude` written for real against the lake's own real `WCESTUS1` (US
crude stocks ex-SPR, Spec 01). `derived.cot.<root>.mm_pct_3y` written for real for all 4
roots (`cl`/`rb`/`ho`/`lco`) against this session's own new, real `pipelines/cftc/` pull.

## `curve.py` — two corrections made to Spec 18's own text during implementation

**`dec_dec` is not deferred to Session C.** The spec's own Session B pseudocode lists
`dec_dec` as one of `time_spreads(unadj)`'s output columns, implying it's computable from
the rank-labelled `unadj` panel alone — but `unadj`'s columns (`f01..fn`) only carry *rank*,
not the real contract code, so there's no way to know which rank is "the December
contract" from `unadj` alone. `core/curve.py::dec_dec(contract_panel)` is instead its own
small function taking the *raw* `contract_panel` (real contract-code columns), reading the
delivery month directly off each code's own fixed CME/ICE month letter (`"z26"` *is* the
December 2026 contract by construction — a universal exchange convention, not something to
look up or guess) — no roll-calendar logic needed at all, so this didn't actually need to
wait for Session C's `roll_calendar()` work.

**Regime codes live in `core/curve.py::REGIME_CODES`, not `series_meta`.** The spec's own
text says the regime int code is "stored as small int, map in `series_meta`" — but
`pipelines/futures/series_meta.py`'s schema (`root, contract, expiry, tick_size,
contract_unit, currency, roll_rule, source`) is per-*contract* metadata; a regime-code-to-
label map is a small, fixed, static enum (7 values — the six named states plus a seventh,
`"flat"`, for the `s12==0` knife-edge the spec's own six states don't cover), not row-level
per-contract data. Storing it there would mean inventing a fake "contract" row per regime
code just to reuse the file. `REGIME_CODES: dict[str, int]` lives as a plain module-level
constant in `core/curve.py` itself instead — any future reader (a page, another spec)
imports this same dict to decode the stored int, matching this project's own "import, don't
guess" precedent for its real functions.

## Business-day arithmetic is plain Mon–Fri, not a real trading calendar

Confirmed with the user before this session: `core/calendars.py` has no business-day
helper at all (only a release-schedule lookup). `core/curve.py`'s roll-date arithmetic uses
`numpy.busday_offset` (weekends only, no CME/ICE holiday awareness) rather than adding a
new trading-calendar dependency — there is no real settlement data yet to need
holiday-exact roll dates against. Revisit if Session C's `roll_calendar()` (GSCI/BCOM
business-day-of-month rules) or real data later demands more precision.

## Verified (Session B)

All 12 `tests/test_core_curve.py` cases pass — roll timing (exact business day, not off by
one), a contract retiring from every rank once rolled past (not just demoted), zero return
on the roll day for a ratio-adjusted series (constructed so the new front contract's own
price is flat across the boundary), `dec_dec` against hand-picked December contracts,
`convexity`'s two spec-given worked examples, all three of `curve_regime`'s spec-given
worked examples plus the undocumented `"flat"` seventh state, `transition_matrix` rows
summing to 1 (and an all-`NaN` row for a state with no observed outgoing transition), and
no-look-ahead (a truncated vs. full-history panel classify day *t* identically).

`pipelines/derived/curve.py` run for real against Session A's own synthetic
`tests/fixtures/futures/settles_synthetic.csv` fixture (`cl`, 2 contracts — `z26`/`f27`):
wrote 6 real rows (`derived.spread.cl.s12` for 3 dates, `derived.curve.cl.regime` for the
same 3, correctly `6` = `"flat"` throughout since only 2 ranks exist — `convexity` needs a
third, so `cv` is `NaN` for every date, and neither the `super_*` states nor the four
`cv`-dependent states can fire, falling through to `"flat"` exactly as designed). Confirmed
`s12` matches the hand-computed `61.35 - 62.05 = -0.70` on the first date exactly. This is a
wiring smoke test on a genuine `n=2` case, not a claim the full 3+-contract algorithm was
exercised against real market data — no real multi-contract settlement data exists yet
(same deferral as Session A); the full algorithmic correctness is what
`tests/test_core_curve.py`'s hand-built synthetic panels cover independently.

Also registered `pipelines.futures.pull_daily` and `pipelines.derived.curve` in
`infra/run_scheduled.py`'s `daily` cadence group (in that order — `derived.curve` reads
what `futures.pull_daily` just wrote) — a real gap from Session A, which built the
entrypoint but never actually wired it into the orchestrator.

## `contract_panel_for` promoted to public (Session D)

`_contract_panel_for` (the settle-pivot logic building a `contract_panel`/`expiries` pair
from the lake + `series_meta`) was renamed to `contract_panel_for` — no behaviour change —
so `apps/dashboard/pages/18_curve.py` could import and call it directly, matching
`pipelines/eia/transforms.py`'s own "page imports a pipeline's transform helper"
precedent instead of re-implementing the same pivot logic a second time.
