# pipelines/derived — notes

Thin steps that read the lake, call pure `core/<topic>.py` analytics functions, and write
`derived.*` series back — never the reverse (`core/` modules never touch DuckDB, per root
NOTES.md). First module in this package on this branch: `fundamentals.py` (Spec 19
Session A). (Spec 18's own `curve.py`/`cushing.py` modules live on the still-open
`feat/futures-settlements` branch and will land here once that PR merges.)

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
