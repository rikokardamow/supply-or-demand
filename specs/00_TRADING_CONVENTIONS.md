# Trading Analytics Layer — Conventions (Specs 18–27)

Read this together with the repo root `NOTES.md` before any session on Specs 18–27. Where this file and `NOTES.md` disagree, `NOTES.md` wins.

## What these specs are
Specs 01–17 build the lake (per-source pipelines) and the publication-facing research pages. Specs 18–27 add a **desk-grade trading analytics layer** on top of the same lake: curve structure, systematic signals, risk, forecast models, options, freight, gas analytics, and a trade journal with the Kardamow validation ledger. They read the lake through `core.storage` only. They introduce **one new upstream data source** (futures settlements, Spec 18) and a small number of manual CSV drops; everything else is derived from what Specs 01–17 already ingest.

## Repo placement (no new package trees)
| Concern | Location | Precedent |
|---|---|---|
| Ingestion | `pipelines/<source>/` via `/new-pipeline`, with `NOTES.md` + cassette test | `pipelines/eia/`, `pipelines/gie/` |
| Pure analytics / models | `core/<topic>.py` — one flat module per spec (`core/curve.py`, `core/systematic.py`, `core/risk.py`, `core/vecm.py`, `core/vol.py`, `core/freight.py`, `core/gas_analytics.py`, `core/fundamentals.py`, `core/macro_signals.py`, `core/journal.py`) | `core/macro.py`, `core/seasonal.py` |
| Chart primitives | add to `core/theme.py` (house style); page-only composites in `apps/dashboard/components/` | `seasonal_range_chart`, `revision_waterfall` |
| Pages | `apps/dashboard/pages/NN_<name>.py` via `/new-page`; every section in `card(title)` | pages 01–15 |
| Tests | `tests/test_<topic>.py`; pure-function tests on synthetic data; vcrpy cassettes only for clients | existing suite |
| Manual data | `data/manual/<source>/*.csv` (git-ignored), loaded by a thin `pipelines/manual_<source>/` reader that writes to the lake with `source="manual"` | `quotas.csv` (Spec 06) |

Pure analytics modules never touch DuckDB; pages never call APIs. Same as today.

## Lake conventions (reuse `core/schemas.py`, do not redefine)
- Series IDs lowercase dotted, per existing style (`fx.usd_eur`, `eia.…`): futures `fut.<root>.<contract>.settle` (e.g. `fut.cl.z26.settle`), derived nearby ranks `fut.cl.f01.settle` … `f36`, spreads `derived.spread.cl.s12`, convexity `derived.curve.cl.cv123`, regime `derived.curve.cl.regime` (stored as small int, map in `series_meta`), positions `derived.pos.<strategy>.<root>`, risk `derived.risk.var01.<root>`.
- Roots: `cl` (WTI), `lco` (Brent), `rb`, `ho`, `g` (ICE gasoil), `ng`, `tfm` (TTF), `nbp`, `jkm`.
- `revision_date` = ingestion time for settlements (they don't revise); manual drops use the file's as-of date.
- Values always `float64` on write (v0.11 lesson). Spreads and convexity are sub-dollar — add a regression test on the futures pipeline that a `0.35` spread reads back as `0.35`, not `0`.
- Publication lag respected at signal time: EIA weekly (Wed for prior Fri), CFTC (Fri for prior Tue), MOMR (mid-month), IP (~6 weeks). A signal at date *t* may only use rows with `date <= t` **and** `release_date <= t`; use `core/calendars.py`.

## Roll-adjusted continuous series
`core/curve.py` owns the nearby construction. Roll `roll_days_before_expiry=5` business days before expiry (parameter). Two outputs are stored: unadjusted ranks (for spreads, always) and ratio-back-adjusted `f01` (for returns only). Never compute a spread from the adjusted series.

## Model pages (Specs 20, 22, 23 and any backtest)
Every model or backtest card shows: estimation window, last refit date, out-of-sample test status vs the named benchmark, exception count, and structural-break test date. Published benchmark figures from the source literature are displayed beside the repo's own estimate with the deviation; a miss is a visible diagnostic, never a silent pass.

## Session protocol (unchanged from NOTES.md, restated)
Plan mode first. One session per sitting. Every session ends with `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines` green, a live in-browser check of the page, and the session's Definition-of-Done boxes ticked in the spec with the verification actually performed. Cross-check at least one real number against an independent source per data session (as every spec so far has done). Never write a secret to a tracked file.

## Copyright
Playbook seeds and model captions carry titles, authors and page references only — no verbatim text from the source books.

## Verified core API

Read directly from `core/schemas.py`, `core/storage.py`, `core/seasonal.py`, `core/theme.py`
and `core/calendars.py` (checked against the real source, not assumed) — import these,
don't re-derive them.

### `core/storage.py` — the lake

```python
def write_ts_long(df: pd.DataFrame, source: str) -> None: ...
def write_flows(df: pd.DataFrame, source: str, replace_window: tuple[datetime, datetime] | None = None) -> None: ...
def write_events(df: pd.DataFrame, source: str) -> None: ...

def read_ts_long(series_ids: list[str] | None = None, start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame: ...
def read_flows(source: str | None = None, start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame: ...
def read_events(start: datetime | None = None, end: datetime | None = None, commodity: str | None = None) -> pd.DataFrame: ...

def warehouse() -> duckdb.DuckDBPyConnection: ...  # registers ts_long/flows/events as DuckDB views
```

- `write_ts_long`/`write_flows` both force `.astype({"value": "float64"})` before writing —
  a spreads/convexity pipeline does not need to add its own float coercion, it's already
  covered, and writing a sub-dollar value (e.g. `0.35`) is safe.
- `write_ts_long`'s de-dup key is `(series_id, ts)`, kept by latest `revision_date` — **not**
  `source`. Every source's rows are physically partitioned separately
  (`data/lake/ts_long/source=<source>/year=<year>/`), so two different sources can safely
  share the same `series_id` (e.g. a manual-CSV futures fallback and a real IBKR pull both
  writing `fut.cl.f01.settle`) without colliding — but note the DataFrame's own `source`
  *column* is a separate, real parquet value from the write call's `source` *parameter*; a
  reused transform function that hardcodes a `source` column (see
  `pipelines/weather/degree_days.py`'s own `"source": "open_meteo"` for a real example of
  this exact gotcha) must have that column explicitly overridden by the caller before
  writing under a different source, or rows get silently misclassified on read-back.
- There is **no `series_meta` table or DuckDB persistence mechanism** anywhere in this
  codebase today (confirmed by reading every function in `core/storage.py`) — Spec 18's own
  text names a `series_meta` table for expiry/roll metadata; the existing precedent for a
  small non-`ts_long` reference table is a plain Parquet file with its own manifest-style
  read/write pair (see `pipelines/weather/anomaly_maps.py`'s `manifest.parquet`), not a new
  DuckDB persisted table — `core.storage.warehouse()` only ever registers views over Parquet
  globs, never writes one.
- `flows` has no `revision_date` column — a revision-aware re-pull needs `write_flows`'s
  `replace_window` param, scoped to the `(from_node, to_node)` pairs actually present in the
  fresh pull (see that function's own docstring for why, and the real bug this project hit
  when that scoping was missing).

### `core/seasonal.py`

```python
def seasonal_stats(df: pd.DataFrame, value_col: str, years: range = range(2018, 2026), exclude: tuple[int, ...] = (2020,)) -> pd.DataFrame: ...
# df needs columns "ts" and `value_col`. Returns one row per day-of-year with columns
# lo/hi/median plus one column per included year. 2020 excluded by default -- never pass
# exclude=() to include it.

def yoy(df: pd.DataFrame, value_col: str = "value") -> pd.Series: ...
# year-over-year % change by day-of-year, most recent two years in the data only.
```

### `core/theme.py` — chart primitives (partial; grep `^def ` in the file for the rest)

Colours: `NAVY = "#0f2a4a"`, `LIGHT_BLUE = "#5b9bd5"`, `RED = "#c0392b"`, `ORANGE = "#e67e22"`,
`GREY = "#95a5a6"`, `BAND = "rgba(150,150,150,0.25)"`, `GRID = "#e6e6e6"`.

```python
def seasonal_range_chart(stats_df: pd.DataFrame, current_year_series: pd.Series, title: str, unit: str, ...) -> go.Figure: ...
def dual_axis_chart(left_series: pd.Series, right_series: pd.Series, title: str, left_label: str, ...) -> go.Figure: ...
def simple_time_series_chart(series: pd.Series, title: str, unit: str) -> go.Figure: ...
def multi_year_overlay_chart(stats_df: pd.DataFrame, title: str, unit: str) -> go.Figure: ...
def current_vs_prior_year_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure: ...  # df needs columns ts, value
def gauge_chart(value: float, title: str, max_value: float = 100.0, thresholds: tuple[float, float] = (50.0, 75.0), ...) -> go.Figure: ...
def hour_day_heatmap(df: pd.DataFrame, title: str, unit: str) -> go.Figure: ...  # df: hourly DatetimeIndex, single value column
def category_time_heatmap(wide_df: pd.DataFrame, title: str, unit: str, center: float = 100.0) -> go.Figure: ...
def production_vs_quota_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure: ...  # df needs columns country, actual_kbd, quota_kbd, compliance_pct
def revision_waterfall_chart(df: pd.DataFrame, title: str, unit: str) -> go.Figure: ...  # df needs columns label, value; red=down, navy=up
def time_series_area_chart(series: pd.Series, title: str, unit: str) -> go.Figure: ...
```

No `core/theme.py` function named `revision_waterfall` exists — the real name is
`revision_waterfall_chart` (this section's own title says "revision_waterfall" further up;
that was a naming slip, not a second function).

### `core/calendars.py` — release scheduling, not a per-row publication-lag check

```python
RELEASES: dict[str, ReleaseSchedule]  # keys confirmed present: "wpsr", "eia_gas_storage",
                                       # "agsi", "baker_hughes", "cftc_cot", "opec_momr", "jodi"
def next_release(name: str, now: datetime) -> datetime: ...
```

This module only answers "when is the next scheduled release after `now`" — it has **no**
function that takes a specific row's date and tells you whether that row's data was already
public by some other date `t`. The "`release_date <= t`" check this file's own §Lake
conventions section describes above does not exist as a callable yet; a Spec 18/19/22 session
that needs it will have to build it (e.g. from `RELEASES`'s own schedule plus each series'
`revision_date`), not import it from here.

### Spec 14 series IDs — verified against the real lake, not assumed

Checked live via `core.storage.read_ts_long()` against the real lake (1,489 distinct
`series_id` values, 1,137,110 rows, as of 2026-09-04) — Spec 14 was never built (see the
open GitHub tracking issue), so neither series this file's own dependency table names as
"exists" for Spec 14 is actually real yet:

- **CFTC COT**: **does not exist in the lake at all** — zero `series_id` values contain
  `"cftc"` or `"cot"`, and no `pipelines/cftc/` (or similarly named) pipeline exists anywhere
  in this codebase. `core/calendars.py`'s `RELEASES["cftc_cot"]` is only a release-time
  schedule entry, not an ingested series. Spec 01's own Stretch section already names a CFTC
  COT overlay as a **skipped stretch item** (see the open GitHub issue for it) — Spec 18/19's
  own COT-percentile work depends on this pipeline being built first; it is not "extend",
  it is "build from scratch".
- **Cushing**: `W_EPC0_SAX_YCUOK_MBBL` (source `"eia"`) genuinely exists — but it is Cushing,
  OK **crude oil stocks** (a Spec 01 series, weekly), not "Cushing working capacity". No
  series with `"cushing"` in its `series_id` beyond this one exists, and no semi-annual
  working-storage-capacity series exists under any name. Spec 18's own text calling
  `eia.cushing_working_capacity` "exists / extend" is not accurate as of this check — it
  needs building, not extending, and should be sourced and verified live (an EIA route, most
  likely `petroleum/stoc/wstk` or a capacity-specific route — check live, do not guess)
  before Spec 18 Session A assumes it.
