# pipelines/eia_storage_capacity — notes

## Not an EIA API route — confirmed live by walking the whole tree

EIA's real v2 API (`api.eia.gov/v2`) has no working/shell storage capacity route anywhere —
confirmed by walking every top-level category and both `petroleum/stoc`'s and
`petroleum/crd`'s own sub-routes live. This data only ever existed as a standalone report,
`eia.gov/petroleum/storagecapacity`, downloaded as an Excel workbook, not fetched via
`EIAClient`'s usual route/facet pattern — this pipeline is its own small package rather than
folded into `pipelines/eia/` for that reason.

## The report is discontinued — confirmed live, not assumed

`eia.gov/petroleum/storagecapacity`'s own page text: *"We have discontinued publication of
the Working and Net Available Shell Storage Capacity report."* Last data-as-of date: 2024-03-01
(released 2024-05-31). This pipeline therefore has **only** `pull_history.py` — no
`pull_daily.py`, and it is **not** registered in `infra/run_scheduled.py` — there is nothing
to re-pull; the source itself will never publish again unless EIA explicitly resumes it, in
which case this pipeline's own scope should be revisited.

## Workbook structure, confirmed live by downloading and parsing the real file

`crudeoilstorage.xlsx` (~78 KB, 7 sheets: `US`, `PADD 1`–`PADD 5`, `Cushing`). This pipeline
only reads the `Cushing` sheet (Cushing-specific coupling is Spec 18's own scope — PADD-level
capacity, if ever needed, is a different session's concern). Real row layout (labels, not
fixed row numbers — matched by prefix in `client.py`, since a hand-maintained government
workbook's exact row position isn't something to hardcode even for a now-frozen file):

- `Pipeline and Tank Farm` / `Tank Farm` / `Pipeline Fill and in Transit by Rail` — stocks
  breakdown (not used here; the lake already has a weekly Cushing stocks series from
  `pipelines/eia/pull_wpsr.py`'s own `petroleum/stoc/wstk` route,
  `W_EPC0_SAX_YCUOK_MBBL`).
- `Tank Net Available Shell Storage Capacity` / `Tank Working Storage Capacity` / `Tank
  Capacity Utilization Rate` — a narrower, tank-only scope (EIA's own footnote 2: "Stocks
  divided by working storage capacity" — i.e. Tank Farm stocks ÷ Tank Working Capacity).
- **`Sum of Working Storage Capacity and Stocks in Transit`** (the row this pipeline
  actually extracts) — EIA's own footnote 3: *"may be used as an estimate of total
  commercial crude oil storage capacity that may be applied to weekly crude oil stocks data
  where details by storage facility are unavailable"* — this is precisely this project's own
  situation: `W_EPC0_SAX_YCUOK_MBBL` is a single undifferentiated weekly total, not split
  tank-vs-pipeline, so it must pair with this broader capacity figure, not the narrower
  tank-only one above it.
- `Alternate Utilization Rate` — EIA's own precomputed utilisation using the same broad
  scope (`Pipeline and Tank Farm` stocks ÷ `Sum of Working Storage Capacity and Stocks in
  Transit`) — used as a real, independent cross-check for
  `core.curve.cushing_utilisation()` in `tests/test_core_curve_session_c.py` (confirmed
  live: `33086 / 80604 = 0.41048` for the 2024-03-01 report, matching the workbook's own
  printed `0.4104759069028832` to full precision).

## Verified (Session C)

A real download and parse confirmed: 23 semi-annual data points, `2011-03-31` through
`2024-03-01`, `eia.cushing_working_capacity` (source `"eia"`, `geo="OK"`,
`freq="semi-annual"`). `pull_history.py` run for real, not synthetic — the source itself
is real, live, government data, just no longer updating.

**Real limitation, stated plainly**: `pipelines/derived/cushing.py::cushing_utilisation()`
forward-fills this sparse capacity series onto the real weekly `W_EPC0_SAX_YCUOK_MBBL`
stocks index — for every week after `2024-03-01` (the report's own last published date),
`derived.cushing.util`/`util_decile` are computed against that same frozen 2024 capacity
figure, not a genuinely current one. Confirmed live: a real end-to-end run against this
project's actual lake produced 803 real weekly utilisation rows, `2026-08-14`'s own
utilisation = `0.264` — plausible, but built on a capacity denominator over two years stale
by that date. This is a real, structural consequence of the source being discontinued, not
a bug — flagged here and in `specs/18_curve-market-structure.md`'s own close-out rather than
silently implied to be current.
