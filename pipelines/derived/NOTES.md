# pipelines/derived — notes

Thin steps that read the lake, call pure `core/<topic>.py` analytics functions, and write
`derived.*` series back — never the reverse (`core/` modules never touch DuckDB, per root
NOTES.md). Modules here: `curve.py` and `cushing.py` (Spec 18 Sessions B/C) and
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

## `cracks.py` — spot legs, because no futures legs exist (Spec 20 Session A)

Confirmed live at the start of the session, not assumed: the lake holds **zero `fut.*`
rows and zero `fut.*` series IDs**. Spec 20's own Data section asks for Spec 18's
unadjusted nearby for `cl`/`rb`/`ho`/`g`/`lco`; none of it exists, because Spec 18's
pipeline has never ingested a real settlement (see `pipelines/futures/NOTES.md`).

So the crack legs are **spot**, from Spec 10's FRED pipeline. Three product legs were
missing and were added to `pipelines/macro/fred_series.py` this session — `DGASNYH`,
`DGASUSGULF`, `DHOILNYH`, each probed live against the FRED API before use rather than
guessed, per the project's own "never guess a series_id" rule. All three run daily back
to 1986-06-02.

Consequences worth knowing before extending this:
- Every series here is `derived.crack.<name>.spot`. `spot` is the only tenor computable
  today; `core.cracks.crack_board`'s `m1`/`m2`/`m6` columns stay `NaN` until real
  futures land, never `0.0` (the sanctions/Adanos "no data isn't zero" precedent).
- `crack_gasoil_nwe` and `crack_sg_go` are implemented and unit-tested but **not** wired
  in — ICE gasoil and Singapore gasoil have no legs in the lake at all. A crack whose
  legs are absent is omitted from `build_cracks` entirely rather than emitted as a column
  of NaN.
- Registered in `infra/run_scheduled.py`'s **`weekly_fri`** group directly after `macro`,
  not `daily`. Spec 20 says the series is "written daily" — it is daily-*frequency*, but
  its legs only refresh on the weekly FRED cadence, so a daily rerun would rewrite
  identical rows from unchanged inputs.
- The crude and product legs have genuinely ragged right-hand ends (FRED publishes
  `DCOILWTICO` a few days behind the product spots — observed live, e.g. WTI ending
  2026-08-25 while the product spots ran to 2026-09-01). `core.cracks` intersects leg
  indices rather than forward-filling, so a crack is only ever computed on a date where
  every leg actually printed.

## Verified (Spec 20 Session A)

45,476 real rows written across 5 cracks. `derived.crack.us321.spot` cross-checked
against a 3:2:1 computed independently from the **EIA API** (`petroleum/pri/spt`) —
60 overlapping days, **max absolute difference 0.0**. Annual means also reproduce known
refining history unprompted: 2015-19 ≈ $17–19, 2020 $10.60, 2022 $41.11, 2025 $21.75.

Spec 20's own worked example `crack_321(70, 2.20, 2.40) = 28.53` is **wrong**; the correct
value is **25.20**. Correction recorded in `specs/20_refining-crack-vecm.md` and in the
test's own docstring.

## `vecm_refit.py` — the model fails out-of-sample, and that is the finding (Spec 20 Session B)

Monthly refit of the crack VECM. Writes a model card to `data/lake/vecm/model_card.parquet`
as a plain Parquet manifest — the `pipelines/futures/series_meta.py` precedent — because a
model card is not a `ts_long` series and `core/storage.py` still has no persisted-table
mechanism. Registered in `infra/run_scheduled.py`'s `monthly` group.

**Read the card before trusting the model.** On real data it reports `oos_status = fail`:

- `theil_u = 1.0725` — the VECM is 7% *worse* than a random walk. DM stat +1.81, p = 0.070
  (significantly worse at 10%), 32 exceptions in 60 forecasts.
- `crack_i1 = False`. ADF and Phillips-Perron disagree on the spot crack in every sample
  window, and PP rejects the unit root decisively (p = 0.008 full sample, 0.000 on the
  paper's 1993-2008 window). A refining margin mean-reverts — it cannot drift without
  bound — so it is not I(1), and the Johansen/VECM framework does not transfer to it.
- `rank = 2` in a two-variable system is the standard signal that the system is already
  stationary, not that there are two cointegrating relations.
- Granger runs the *opposite* way to Murat & Tokat: crack->spot p = 0.442 (nothing),
  spot->crack p = 0.038.

None of this is a bug in the implementation — all three of the spec's synthetic acceptance
tests pass (beta recovered at 0.1611 against a 0.16 target, the obs-120 break found at
exactly 120, the random-walk look-ahead guard holds). The cause is the **spot legs**: the
paper models crack *futures*, and the lake has no futures at all. Revisit the whole
specification once Spec 18 ingests real settlements.

**Do not tune the specification until it passes.** The conventions require a miss to be a
visible diagnostic; the card carries `deviation` so the caveat travels with the numbers
rather than living only in a docstring.

### April 2003 was not recovered

Bai-Perron with one break finds 2005-03 (+23 months); Andrews sup-F finds 2004-08 (+16).
The 2004-05 crude run-up is a far larger level shift and dominates the search. Allowing two
breaks surfaces 2003-01, three months from the paper's date — partial recovery obtained by
relaxing the break count, not a clean replication. Recorded as a miss in the spec.

## `eu_gas_balance.py` — EU-27 gas balance by route (2026-10-26)

Inputs: `estat.gas.*` (`pipelines/eurostat_gas`), the committed `eu_gas/routes.csv` and
`eu_gas/assumptions.csv`, and GIE `agsi.EU.*`. Arithmetic is `core/eu_gas_balance.py`.
**Read `derived.eu_gas.*` only through `latest_run`.** Each run writes the whole model, and a
month later found incomplete (2024-03) or a projection overtaken by data would otherwise
linger in the lake. Routes are net imports. Intra-EU trade is excluded. Months whose partner
detail does not add up to the total are left out. Blank EU balance cells are rebuilt from
member states only at 99% coverage, and flagged in `derived.eu_gas.member_sum.*`. Not
scheduled. Detail in `eu_gas/README.md`.

## `uk_gas_balance.py` — UK gas balance and the call on LNG (2026-10-26)

Inputs: `desnz.gas.*` (`pipelines/desnz_gas`), the committed `uk_gas/routes.csv` and
`uk_gas/assumptions.csv`, and `derived.eu_gas.route.uk` for the mirror check (skipped if the EU
model has not run). Arithmetic is `core/uk_gas_balance.py`, and the shared projection is
`core/gas_projection.py`. Read through `eu_gas_balance.latest_run`. The projection solves for
LNG as one total; LNG routes are never projected one by one. Detail in `uk_gas/README.md`.

## `eu_carbon.py` — EU ETS allowance balance and auction prices (2026-10-26)

Inputs: `eex.*` and `eu_ets.*` (`pipelines/carbon`), `pipelines/carbon/maritime_phase_in.csv`
and `eu_carbon/assumptions.csv`. Arithmetic is `core/carbon_balance.py`. The projection is
`core/gas_projection.project(..., freq="YS")`, which is annual. Read through
`eu_gas_balance.latest_run`. The balance covers complete registry years only, and the
cumulative surplus carries into the projection. Shipping is a real zero before
`SHIPPING_FROM` (2024), never a gap. Detail in `eu_carbon/README.md`.
