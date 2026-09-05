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

### Contract codes must not collide with nearby ranks (found live, 2026-09-05)

This file's own two examples are in tension: futures contracts as `fut.cl.z26.settle`
(month letter + **two**-digit year) and derived nearby ranks as `fut.cl.f01.settle` …
`f36`. January's exchange month letter is **F**, so a January contract with a two-digit
year in 01–36 is *indistinguishable from a rank*: `fut.cl.f27.settle` reads equally as
"the January 2027 contract" and "nearby rank 27".

This was not hypothetical — eight such series (`fut.lco.f27.settle` … `f34.settle`, the
Jan-2027 to Jan-2034 Brent contracts) were live in the lake before it was caught, while
building Spec 21, the first spec that reads rank series directly.

**The rule:** a contract code must never match `f(0[1-9]|[12][0-9]|3[0-6])`.
`pipelines/futures/client.py::looks_like_rank_code` is the single definition, and
`ManualCSVClient._validate` rejects any drop that violates it, with the fix in the error
message. `pipelines/futures/barchart_curve.py` emits four-digit years (`f2027`, `z2026`)
throughout, which cannot collide by construction. Non-January two-digit codes (`z26`) are
unambiguous and still accepted from exchange-native sources, so IBKR/manual codes are
passed through as the exchange writes them — prefer four digits in anything new.

## Roll-adjusted continuous series
`core/curve.py` owns the nearby construction. Roll `roll_days_before_expiry=5` business days before expiry (parameter). Two outputs are stored: unadjusted ranks (for spreads, always) and ratio-back-adjusted `f01` (for returns only). Never compute a spread from the adjusted series.

## Model pages (Specs 20, 22, 23 and any backtest)
Every model or backtest card shows: estimation window, last refit date, out-of-sample test status vs the named benchmark, exception count, and structural-break test date. Published benchmark figures from the source literature are displayed beside the repo's own estimate with the deviation; a miss is a visible diagnostic, never a silent pass.

## Degenerate inputs fail loudly — never substitute silently
An absent, empty or degenerate input must stop the computation and say why. It may never be
silently replaced with a plausible stand-in, because a plausible-looking series is
indistinguishable from a correct one everywhere downstream: no test fails, no console warns, and
the wrong numbers reach a page carrying the same authority as right ones. Prefer, in order:
raise with the reason; or emit all-NaN so the existing `dropna()` paths drop the rows and nothing
is written; or record the skip with its cause. Never fall back to a different series.

Four instances of this one pattern surfaced in Spec 21 alone, which is why it is written down:

| Substitution | What it would have produced |
|---|---|
| Raw `f01` rank standing in for `derived.curve.<root>.f01_adj` when the adjusted series was absent | Every roll step scored as momentum; `MOM_100` and `VALUE_OVERLAY` still emit full, plausible position series |
| Outright front-month returns standing in for spread P&L on `traded="spread"` strategies | `CONVEX_SPREAD` reads Sharpe **+0.35** instead of **−0.42** — a losing strategy shown as a winning one |
| `np.log` on the 2020-04-20 −$37.63 WTI settle | A silent NaN propagating through momentum and value (fixed by `core.systematic.log_price`) |
| A dollar spread change divided by spot price near zero | Calendar-spread annualised vol inflated 11.6% → 93.8%, three April-2020 days doing all of it (fixed by `core.backtest.spread_to_return`) |

The guardrail path in `core/strategies.py` (`required_ranks` / `missing_ranks` /
`available_strategies`, and `build_positions` raising rather than returning a flat series) is the
reference implementation. `StrategyInputs.guardrail_inputs` is the reference for the all-NaN
variant: an absent conditioner must never silently flatten a real position.

## Provenance of published benchmark figures
A number displayed as a published benchmark borrows the authority of the source it names, so the
page must say where the chain actually stops. Figures transcribed into a spec from a book and then
into code have been verified against the *spec*, not against the *book*; say so, rather than
letting a column headed "published Sharpe" imply a check nobody performed. Spec 21's anchors
(20.3%/0.53, 24.7%/0.64, IR 0.50) are transcribed from `specs/21_systematic-engine.md:5`, which
cites Bouchouev ch. 5–6; none has been checked against Virtual Barrels itself.

Never subtract a repo estimate from a published anchor computed on a different construction. A
C(1,3) Sharpe minus a C(1,13) anchor yields a number that looks like a result and is not; withhold
the deviation and state why.

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

### `core/schemas.py` — full column lists (the only four schemas that exist)

```python
class TsLongRecord:    series_id: str; source: str; ts: datetime; value: float; unit: str; geo: str; freq: str; revision_date: datetime
class FlowsRecord:     source: str; from_node: str; to_node: str; value: float; unit: str; ts: datetime; mode: str
class EventsRecord:    event_id: str; ts: datetime; headline: str; source: str; url: str; tags: list[str]; geo: str; commodity: str; severity: int; language: str
class SanctionsRecord: sanction_id: str; name: str; entity_type: str; programs: list[str]; vess_type: str | None; vess_flag: str | None; vess_owner: str | None; call_sign: str | None; remarks: str | None; imo: str | None; first_seen: datetime; last_seen: datetime; status: str; energy_related: bool
```

`flows` has no `revision_date`; `SanctionsRecord` has no `source` column at all (it's a
single-source, OFAC-only current-state table — see `core/freshness.py`'s own synthetic
freshness key for how Spec 13 special-cased this). No fifth schema exists — a Spec 18
`series_meta` table is not one of these four and has no home yet (see above).

### `core/settings.py` — no futures/IBKR fields exist yet

Required: `eia_api_key, ember_api_key, gie_api_key, entsoe_api_key, fred_api_key`. Optional
(all `str | None = None`): `newsapi_key, worldnews_key, aisstream_key, opensky_client_id,
opensky_client_secret, mapbox_token, tomorrow_io_key, guardian_key, adanos_api_key,
anthropic_api_key`. **No `futures_source`, `ibkr_host`/`ibkr_port`, or any futures-related
field exists today** — Spec 18 Session A needs to add these to `Settings` (and
`.env.example`) itself; this is new work, not a lookup.

### Pipeline source-naming conventions — checked live, genuinely inconsistent across sources

`pipelines/fred/` **does not exist** — the FRED client lives at `pipelines/macro/`
(`fred_series.py`), alongside Frankfurter FX and Eurostat ESI. `pipelines/gie/` and
`pipelines/eia/` exist as named. Reading each pipeline's own `NOTES.md` and the real lake
together: the "series IDs lowercase dotted" convention this file states above is **aspirational
for newer sources but not universal**:
- FRED (`source="fred"`): genuinely lowercase-dotted, `fred.<lowercase_fred_id>` (e.g.
  `fred.dcoilwtico`).
- GIE (`source="gie"`): lowercase-dotted with an uppercase 2-letter country segment,
  `agsi.{COUNTRY}.{field}` / `alsi.{COUNTRY}.{field}` (e.g. `agsi.DE.full_pct`).
- Weather (`source="open_meteo"`/`"gfs"`/etc.): lowercase-dotted, `hdd.{city}.{base}` /
  `hdd.{region}.popw`.
- **EIA (`source="eia"`) breaks the convention entirely**: `series_id` is the raw, uppercase
  EIA API code verbatim (`W_EPC0_SAX_YCUOK_MBBL`, `NW2_EPG0_SWO_R48_BCF`) — no `eia.` prefix,
  no lowercasing. This file's own §Lake conventions example (`eia.…`) and Spec 18's Data
  table (`eia.w_epc0_sax_ycuok_mbbl`, lowercase) are both **wrong as literal series_id
  strings** — the real value to filter on is `W_EPC0_SAX_YCUOK_MBBL` with `source == "eia"`,
  not a `eia.`-prefixed lowercase string. Any Spec 19+ code that joins against an EIA series
  by guessing a lowercase-dotted name will silently match nothing — always confirm via
  `read_ts_long()["series_id"].unique()` first, per this project's own long-standing
  "don't guess IDs" rule.

### Verified series IDs — checked live against the real lake, not assumed

Checked live via `core.storage.read_ts_long()` (1,489 distinct `series_id` values,
1,137,110 rows, as of 2026-09-04):

| Series | Real `series_id` | `source` | Exists? |
|---|---|---|---|
| WTI spot (Spec 10) | `fred.dcoilwtico` | `fred` | yes |
| Brent spot (Spec 10) | `fred.dcoilbrenteu` | `fred` | yes — the only Brent series anywhere in this project |
| Henry Hub spot (Spec 10) | `fred.dhhngsp` | `fred` | yes |
| Cushing stocks (Spec 01) | `W_EPC0_SAX_YCUOK_MBBL` | `eia` | yes (crude oil **stocks**, weekly) |
| Cushing working capacity (Spec 14) | — | — | **no** — Spec 14 never built; no semi-annual capacity series exists under any name |
| CFTC COT, all series (Spec 14) | — | — | **no** — no `cftc`/`cot` series_id anywhere, no pipeline exists |
| EIA gas storage L48 + 7 regions (Spec 05) | `NW2_EPG0_SWO_R48_BCF` + `NW2_EPG0_{SWO,SSO,SNO}_R{31-35}_BCF` (8 total) | `eia` | yes |
| AGSI fill (Spec 02) | `agsi.{COUNTRY}.full_pct` (+ `gas_in_storage`, `injection`, `withdrawal`, `working_gas_volume`) | `gie` | yes, 20 EU countries |
| HDD/CDD (Spec 08) | `hdd.{city}.{base}` / `cdd.{city}.{base}` (14 cities) + `hdd.{eu,us}.popw` pop-weighted aggregates, `.forecast`-suffixed forecast rows | `open_meteo`/`open_meteo_forecast`/`gfs` (multi-source per series_id since the v1.1 GFS addition) | yes |

### Mismatches — spec text vs. real code, checked live

Every item below is a genuine discrepancy between what a trading-layer spec's text
currently says and what actually exists, found by reading the real source rather than
trusting the spec. This pass covered Spec 18 in full (today's spec) and the cross-cutting
infrastructure every later spec assumes; Specs 19–27 were checked only via the runbook's
own one-paragraph summaries, not their full spec text — each spec's own opening session
should re-verify its own specific function/series references against this section before
importing them, the same way this pass did for Spec 18.

- **`eia.w_epc0_sax_ycuok_mbbl` / `eia.cushing_working_capacity`** (Spec 18 Data table) —
  real series_id is `W_EPC0_SAX_YCUOK_MBBL` (uppercase, no `eia.` prefix, `source="eia"`
  is a separate column); the working-capacity series does not exist at all. See above.
- **CFTC COT** (Spec 18/19 dependency) — does not exist; no pipeline. See above.
- **`pipelines/fred/`** (implied by "read eia/gie/fred pipeline NOTES.md") — the real
  path is `pipelines/macro/`.
- **`revision_waterfall`** (this file's own §Repo placement table, and the runbook's §2
  table) — the real `core/theme.py` function is `revision_waterfall_chart`.
- **`series_meta`** (Spec 18 Sessions A/B/C, this file's own §Lake conventions) — no such
  table, or any persisted-DuckDB-table mechanism at all, exists in `core/storage.py`. The
  established precedent for small non-`ts_long` reference data is a plain Parquet
  manifest file (`pipelines/weather/anomaly_maps.py`'s `manifest.parquet`), not a DuckDB
  table — Session A will need to either introduce a first-of-its-kind persisted DuckDB
  table (a real architectural step, flag it explicitly rather than doing it silently) or
  follow the manifest-file precedent instead.
- **Business-day arithmetic** (Spec 18 Session B's `roll_days_before_expiry=5`, Session C's
  `roll_calendar` "business days 5–9") — `core/calendars.py` has no business-day helper at
  all, only a release-schedule lookup (`RELEASES`/`next_release`). Plain
  `pandas.tseries.offsets.BDay` covers generic weekends but not real exchange holidays
  (CME/ICE) — decide explicitly whether that approximation is good enough for a 5-day roll
  window before Session B assumes a real trading-calendar library is unnecessary.
- **`release_date <= t` signal-timing check** (this file's own §Lake conventions) — no
  such function exists; only `core/calendars.py`'s schedule-lookup and each series' own
  `revision_date` exist to build one from.
- **`core.settings.Settings`** has no futures/IBKR-related fields — `FUTURES_SOURCE` and
  any IBKR host/port settings are new additions for Session A, not existing lookups.
- **`ib_insync`** is not a project dependency yet (confirmed via `pyproject.toml`) — adding
  `IBKRClient` needs it added, per root `NOTES.md` rule 7 ("ask before adding a
  dependency").
