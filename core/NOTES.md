# core/ — notes

## Incident: `value` silently corrupted to `int64` project-wide (fixed 2026-09-02)

**What happened**: `core/storage.py::_read`/`_register_view` read every dataset's
parquet files via a single glob (`read_parquet('data/lake/ts_long/**/*.parquet', ...)`
with a bare `SELECT *`). `pipelines/opec_momr`'s Baker Hughes rig-count pipeline had
written its own `value` column as a genuinely int64-typed parquet column (rig counts
are real whole numbers, and nothing at write time forced float64) — every other
source's files correctly used `double`. DuckDB's *default* schema resolution across a
heterogeneous glob (positional, effectively "first file wins") silently coerced the
**entire** `value` column to int64 for **every reader of the whole dataset**, not just
Baker Hughes' own rows. This was invisible for months across many specs because most
series here have large-magnitude values (e.g. crude stocks in thousands of barrels) —
losing the fractional part is imperceptible on a chart. It became blatant while
building Spec 10's FX series: `fx.usd_eur` (a rate that's genuinely always near 1.0)
came back as **exactly `1.0` for every single date**, since every real value in that
range rounds to 1 once truncated to an integer.

**Confirmed live, not assumed**: reading a single file directly with plain pandas
(`pd.read_parquet(one_file)`) always returned the correct `double` value — the
corruption only happened via DuckDB's own glob-based multi-file scan. An outer
`CAST(value AS DOUBLE)` in the SQL alone did **not** fix it either — the truncation
happens at the physical *scan* stage, before any SQL-level expression ever sees the
value. The actual fix is `read_parquet(glob, ..., union_by_name=true)`, which makes
DuckDB match columns **by name** across files and resolve to a safe common type
(double) instead of truncating. Confirmed by testing directly against the real,
already-corrupted lake: without `union_by_name`, a raw `SELECT value` still returned
int64/`1`; with it, real values (`0.86371`, etc.) came back correctly.

**The fix, three layers** (`core/storage.py`):
1. `read_parquet(..., union_by_name=true)` in both `_read` and `_register_view` — the
   actual mechanism that prevents the destructive scan-level truncation.
2. `_typed_select()` — every column explicitly `CAST` to its canonical
   `TS_LONG_SCHEMA`/`FLOWS_SCHEMA`/`EVENTS_SCHEMA` type in the outer `SELECT`. Kept as
   defense in depth even though layer 1 alone fixed the reproduced incident — guards
   against a different kind of type mismatch `union_by_name` might not resolve safely
   on its own, and self-documents the expected output type of every read.
3. `write_ts_long`/`write_flows` now `.astype({"value": "float64"})` before writing —
   a future int-only source (another rig-count-style pipeline, say) can no longer
   write a physically-int64 column in the first place. `validate_ts_long`'s own
   numeric-dtype check accepts int64 as "numeric" (correctly, per the pydantic-style
   validation this project uses elsewhere), so it never caught this on its own.

The physical Baker Hughes parquet files were also repaired in place (recast to
`double` via `pyarrow`) for full consistency, though the read-side fix alone already
neutralises the bug regardless of any file's on-disk type.

**Regression test**: `tests/test_storage.py::
test_read_ts_long_is_not_corrupted_by_an_int64_typed_value_column_in_another_source`
deliberately writes a raw int64-typed parquet file for one source (bypassing
`write_ts_long`'s own coercion, to reproduce the original bug's exact conditions)
alongside a normal float source, and asserts both read back correctly.

**If you ever add a new dataset/schema to this lake**: don't add a fourth `SELECT *`
read path that skips `union_by_name=true` and `_typed_select()` — this incident is
exactly what happens without both.
