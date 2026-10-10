# pipelines/futures — Claude Code Guide

## No IBKR Gateway/TWS running on this machine — confirmed live, not assumed

A direct port check (`127.0.0.1:7497/7496/4002/4001`) at the start of this session found all
four closed/unreachable — matching the earlier Spec 07 deferral finding for the same reason.
`settings.futures_source` therefore defaults to `"manual"`, and `ManualCSVClient` is the only
client verified against real code paths this session. `IBKRClient` is structurally complete
(built against the real `ib_async` API, inspected live via `inspect.signature` rather than
guessed) but only fixture-tested against a mocked `ib_async.IB` — never connected to a real
gateway. Confirmed with the user: they plan to open a real IBKR Gateway themselves later and
come back for the live verification pass at that point; this session does not fabricate a
settlement number to fake that DoD box.

## `ib_async`, not `ib_insync`

The spec's own text names `ib_insync` throughout. Confirmed with the user before adding the
dependency: `ib_insync`'s original maintainer archived that project; `ib_async` is the
actively-maintained, API-compatible community fork (same class names — `IB`, `Future`,
`ContractDetails` — confirmed live via `from ib_async import IB, Future`). Real signatures
checked live, not guessed from the spec's own text:

```python
IB.connect(host: str = "127.0.0.1", port: int = 7497, clientId: int = 1, timeout: float = 4, ...)
IB.reqContractDetails(contract: Contract) -> list[ContractDetails]
IB.reqHistoricalData(contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, ...) -> BarDataList
Future(symbol="", lastTradeDateOrContractMonth="", exchange="", localSymbol="", multiplier="", currency="", **kwargs)
```

`IBKRClient.get_settles` requests daily bars (`barSizeSetting="1 day"`, `whatToShow="TRADES"`)
-- `reqHistoricalData`'s own bars carry `close`/`volume` but **no open interest field**;
`oi` is written as `None` for IBKR-sourced rows and dropped by `to_ts_long.py` rather than
faked as `0.0` (matching the sanctions/Adanos "no data isn't zero" precedent). A real
manual-CSV drop, by contrast, is expected to carry a real `oi` column per the spec's own
CSV schema.

## `series_meta` is a Parquet manifest, not a new DuckDB table

`core/storage.py` has no persisted-DuckDB-table mechanism anywhere (confirmed in
`specs/00_TRADING_CONVENTIONS.md`'s Verified core API section) — `series_meta.py` follows
`pipelines/weather/anomaly_maps.py`'s `manifest.parquet` precedent instead: append +
`drop_duplicates(subset=["root", "contract"], keep="last")`, so a corrected contract spec
simply overwrites the earlier one on the next write.

### Its directory comes from `core.storage.LAKE_ROOT`, resolved per call (2026-10-10)

`series_meta.py` held its own module-level `SERIES_META_DIR` built from a relative path at
import time. Two consequences, both found by a test that had been passing for the wrong
reason: the manifest's location depended on the process's working directory, and patching
`core.storage.LAKE_ROOT` — the one knob every other test uses to isolate the lake — did not
move it, so a test that believed it was writing to `tmp_path` was writing to the real
manifest and only `chdir` was saving it.

It now does `from core import storage` and reads `storage.LAKE_ROOT` inside each function,
so the directory resolves when the call happens rather than when the module is imported.
Call-time resolution is the whole point: `from core.storage import LAKE_ROOT` would rebind a
copy at import and defeat `monkeypatch.setattr` exactly as the old constant did. Verified by
checking the real manifest's mtime across a full `AppTest` run that patched only
`LAKE_ROOT`.

## `contract_specs.csv` — well-known public exchange specs, not fetched live

Per-root `tick_size`/`contract_unit`/`currency` for the 7 roots (`cl`/`rb`/`ho`/`ng` on
NYMEX, `lco`/`g`/`tfm` on ICE) — these are standard, publicly documented CME/ICE contract
specifications (same "small hand-maintained reference file" precedent as
`pipelines/opec_momr/quotas.csv`/`pipelines/weather/cities.csv`), not fetched from any live
API (there is no such API — exchange contract specs are published reference documents, not
a data feed). **Re-confirm each root's values against the exchange's own current
contract-specification page before relying on them for a real trading calculation** — they
were not independently re-verified against a live source this session, unlike every other
number in this pipeline.

## Why `ManualCSVClient`'s CSV schema doesn't carry `tick_size`/`contract_unit`/`currency`

The spec's own settles CSV column list is `date, root, contract, settle, oi, volume,
expiry` — no contract-spec fields. `list_contracts()` joins the settles data's own
per-contract `expiry` against `contract_specs.csv`'s per-root statics to build a complete
`ContractMeta`, rather than requiring the operator to repeat static exchange facts in every
daily settlement drop.

## Verified (Session A)

Both clients built behind the `FuturesClient` protocol. `ManualCSVClient` and the
`settles_to_ts_long`/`series_meta` write path verified against a small, clearly-labelled
synthetic fixture (`tests/fixtures/futures/settles_synthetic.csv`) — not real market data.
Float64 regression test (a `61.35` settle and a `0.35` spread-like value, alongside a
deliberately int64-typed sibling source in the same glob) passes, mirroring
`tests/test_storage.py`'s existing v0.11 guard exactly.

**Not done this session, left open in the spec's own DoD**: the live cross-check against
CME/ICE's published daily settlement bulletin, and the real two-runs-same-row-count
idempotency check — both need real data (a real manual CSV, or a working IBKR Gateway) that
doesn't exist yet. Revisit once the user has either.

## Post-session review pass — real bugs caught before this ever ran against real data

An 8-angle review (correctness, removed-behaviour, cross-file, reuse, simplification,
efficiency, altitude, conventions) against this session's own diff surfaced several genuine
issues, fixed before merging:

- **Duplicate-row check was keyed on `(date, contract)`, not `(date, root, contract)`** —
  contract codes are month+year only (e.g. `"z26"`), shared across every root trading that
  expiry cycle, so `cl/z26` and `ng/z26` on the same real date are both genuinely valid rows,
  not a duplicate. The old key would have rejected any real multi-root settlement CSV drop
  outright. Fixed in `ManualCSVClient._validate`.
- **`source` was hardcoded as `"futures"` in every `ts_long` write, regardless of which
  client actually produced the data** — contradicts this project's own documented
  multi-source-per-partition design (`specs/00_TRADING_CONVENTIONS.md`'s own "Mismatches"
  section already flags the general gotcha class this falls into: a reused write path
  hardcoding a `source` column, exactly what `pipelines/weather/degree_days.py` hit and fixed
  earlier). Switching `FUTURES_SOURCE` between `"manual"` and `"ibkr"` would have silently
  overwritten the other provider's rows for the same `(series_id, ts)` key instead of the two
  coexisting side by side, the way `series_meta.py` (already provider-aware) always did. Fixed
  by threading the real `settings.futures_source` value through `to_ts_long.py` and
  `write_ts_long`'s own `source` parameter explicitly, never a literal string.
- **`ManualCSVClient` didn't lowercase contract codes** the way `IBKRClient.list_contracts`
  already does — an operator's hand-typed CSV isn't guaranteed to use lowercase codes, and a
  mixed-case code would have broken the lake's lowercase-dotted `series_id` convention. Fixed.
- **Duplicate-row validation ran on raw, unparsed date strings** — two rows for the same real
  calendar day written as different strings across separate drops (e.g. a corrected re-drop
  as `"2026-9-1"` vs the original `"2026-09-01"`) would have slipped past a string-level
  comparison. Fixed by parsing dates before validating, not after.
- **`pull_daily.py`'s "trailing 5 days" was actually a 6-day inclusive window** (`today -
  timedelta(days=5)` through `today` is 6 calendar days, not 5) — a real off-by-one against
  the stated intent. Fixed; the date-window arithmetic is now its own small, directly-tested
  `trailing_window()` function rather than inline in `main()`.
- **`pull_history.py`/`pull_daily.py` duplicated their entire per-root pull loop**, with
  `pull_daily.py` reaching into `pull_history.py`'s own underscore-prefixed "private"
  `_series_meta_rows` across module boundaries. Factored into a shared `pipelines/futures/
  pull.py::pull_root()`, matching `pipelines/entsoe`'s own precedent of one shared `pull_*()`
  helper both entrypoints call with different date windows.
- **`to_ts_long.py` re-read `contract_specs.csv` from scratch a second time** just to recover
  a `currency` value the caller had already computed into `ContractMeta` moments earlier —
  fixed by threading `contracts: list[ContractMeta]` through `settles_to_ts_long` instead.
  This also fixed a related semantic gap: `unit` was a bare currency code (`"USD"`), unlike
  every other pipeline's `unit` convention (a real unit-of-measure string a chart axis can
  label directly, e.g. `"GWh/d"`, `"degree-days"`) — now `f"{currency}/{contract_unit}"`
  (e.g. `"USD/1000 bbl"`).

**Reviewed and deliberately left as-is (documented, not fixed)** — these all concern the
`IBKRClient` path, which is unexercised this session and whose real shape (rate limits,
pacing behaviour, real chunking needs) can't be known until a live Gateway is connected;
fixing them now would be speculative hardening against an unverified interface, which this
project's own "smallest change that satisfies the spec's acceptance criteria" rule argues
against:
- `IBKRClient` opens and closes a fresh Gateway connection separately in `list_contracts` and
  `get_settles` (two connects per root instead of one) — revisit once real pacing/rate-limit
  behaviour is observed.
- `IBKRClient.get_settles` has no chunking for a multi-decade `pull_history.py` backfill
  request — IB's real historical-data API enforces duration limits per bar size that a
  single `reqHistoricalData` call spanning 1993-present will not satisfy; needs real chunking
  logic once verified live, not guessed now.
- `IBKRClient.get_settles`'s per-contract `except Exception: print(...)` prints the raw
  exception unsanitised — unlike `pipelines/entsoe`'s own credential-leak-driven convention
  of sanitizing first. Confirmed this session that IBKR Gateway auth has no query-string
  token or API key to leak (host/port/clientId only), so there's nothing sensitive to leak
  *today* — but if a future IBKR error variant ever embeds account or session info, this has
  no gate. Worth a sanitizing wrapper once the live path is actually exercised.
- `load_contract_specs()` (a 7-row CSV) is read independently up to 3 times per root inside
  `client.py` — real but negligible given the file's size; not worth threading a cache through
  for Session A's scope.
- `series_meta.py`'s dedup key (`root`, `contract`) doesn't include `source` — a manual-CSV-
  sourced contract spec and a later IBKR-sourced one for the same contract silently overwrite
  each other. Left as-is because contract specs (`tick_size`/`contract_unit`/`currency`) are
  meant to be objective per-contract facts both providers should agree on, not
  provider-specific data — the `source` column still records provenance for debugging.

## Real futures data finally exists (2026-09-05)

Spec 18 Session A left this pipeline built but empty -- no `fut.*` row had ever been
written. Three sources now exist, covering different ends of the problem. All three
write the conventions' own series ids, partitioned by `source`, so they coexist.

| Source | What | Span | Rows |
|---|---|---|---|
| `eia_futures.py` | NYMEX ranks 1-4, WTI/RBOB/HO/pre-2006 unleaded | 1980-01-02 -> 2024-04-05 | 113,661 |
| `barchart_curve.py` | Brent Financial, full 89-month outright curve | 2026-09-04 only | 89 |
| `client.py::IBKRClient` | live + full curve | not yet connected | 0 |

### `eia_futures.py` -- history, from a discontinued route

EIA's `petroleum/pri/fut` publishes real NYMEX settlements for contracts 1-4, free,
through the same API key Spec 01 already uses. **The route is discontinued**: it stops at
2024-04-05 (confirmed against the route's own metadata, while `petroleum/pri/spt` runs to
the present). So it is a history source and cannot drive a live board.

It gives *ranks*, not contract codes -- no expiry, open interest or volume -- so it
bypasses `core/curve.py::nearby_panel` (which derives ranks *from* codes plus expiries)
and writes `fut.<root>.f01..f04.settle` directly. Consequences: `s12`/`s13`/`cv123` are
computable; Dec-Dec spreads, the roll calendar, `series_meta` rows and anything past rank
4 are not.

RBOB (`rb`, from 2005-10) and pre-2006 NYMEX regular unleaded (`hu`, to 2006-12) are kept
as **separate roots**. They are different contracts; splicing them at ingestion would bake
an analytical decision into the lake. `core.cracks.rbob_splice_flag` exists for exactly
this splice, and it is a downstream choice.

### `barchart_curve.py` -- one date, but the whole curve

A Barchart futures-spreads export carries no outright prices, only `SP` (leg1-leg2), `SA`
(strip average of its legs) and `BF` (butterfly, ignored). `SA` and `SP` on the same pair
pin both outrights (`a = SA + SP/2`); every other contract then follows from a spread
against an already-solved one. Spreads alone fix only the curve's *shape*, so with no `SA`
anchor `reconstruct_curve` raises rather than returning a curve wrong by a constant.

**Validated against a real published quote**: rebuilt from spread rows alone, the
2026-09-04 Brent front month comes out at **96.280** against Barchart's own **96.28s**
settlement, the over-determined anchors agree to half a cent, and an implied QAZ6-QAF7 of
3.17 matches the separately quoted 3.17 exactly.

Barchart's `QA` is Crude Oil Brent Financial (NYMEX) -> root `lco`. **Confirmed with the
user, not inferred from the price level** -- the level was merely consistent with Brent.
`PRODUCT_ROOTS` is the map; an unknown product is skipped, never guessed.

`source="manual"`: these settles are *reconstructed from a vendor export*, not an exchange
settlement feed, and must not pose as one.

### IBKR -- infrastructure ready, still not connected

`ibkr_preflight.py` is a readiness check that runs without a Gateway
(`python -m pipelines.futures.ibkr_preflight`). It probes all four ports, reports which
are open, flags a `settings.ibkr_port` that points somewhere closed, and prints the exact
next step. Every earlier session recorded "all four ports closed" by hand; this makes that
reproducible. Current status on this machine: all four closed, `FUTURES_SOURCE=manual`.

`IBKRClient.get_settles` now **chunks its requests** (`duration_windows`,
`IB_MAX_DAYS_PER_REQUEST = 365`). This was flagged in this file as a known gap that would
break on first real use, and it would have: `pull_history` sends a single multi-decade
`durationStr`, which IB rejects outright. Windows share their boundary date rather than
leaving a one-day gap -- the duplicate bar is removed by the lake's own `(series_id, ts)`
de-dup, whereas a gap would silently lose a settlement.

Still open on the IBKR path, unchanged and still unverifiable without a live Gateway: two
connections per root, and the unsanitised exception print.

## Serving-layer publish: `publish_curve.py` (Spec 32 Session 3, live 2026-09-09)

`python -m pipelines.futures.publish_curve` reads the lake's `fut.*` series and publishes
them into Supabase's `serving.curve_settles` and `serving.spreads`. It runs in
`infra/run_scheduled.py`'s `daily` group, after the `futures` pull it reads behind.

### The two lake shapes feed one table each — deliberately

`serving.curve_settles.contract` wants a real contract code (the spec's own example is
`'BRNX6'`). A *rank* is not a contract, so the two shapes documented above are not
interchangeable here:

| Lake shape | Source | Serving table | Why |
|---|---|---|---|
| `fut.lco.<monthcode><year>.settle` | `manual` | `curve_settles` | genuine contract codes |
| `fut.<root>.f01..f04.settle` | `eia` | `spreads` | ranks, and where the real history is |

`root` and `contract` are the lake's own values uppercased (`lco` → `LCO`,
`x2026` → `X2026`) — no re-mapping to an exchange ticker, because nothing in the lake
records one. `expiry` and `oi` are published as NULL: the Barchart reconstruction carries
neither, and a guessed expiry would be fabricated market data.

### Only five spread legs are computable

Ranks 1–4 are all that exist, so `spreads` holds `M1-M2`, `M1-M3`, `M1-M4`, `M2-M3` and
`M3-M4` only. **`M1-M12` appears in Spec 32's own `legs` example and is not published** —
it needs an `f12` this lake has never held. It is omitted loudly (here and in the
`source_note` on every `publish_log` row), never filled with a guess.

Sign convention is `core.curve.time_spreads`' own — front minus back (`M1-M2` = `f01` −
`f02`), so positive is backwardation. `tests/test_publish_curve.py` asserts the equality
against `time_spreads` directly rather than restating the rule, so the two cannot drift.

### Rank coverage is uneven, and the inner join is what handles it

Only dates where **both** legs have a real value produce a row — an inner join, never a
fill. This is not theoretical: EIA's own `cl` history starts `f03` on 1983-03-30 but
`f02`/`f04` only on 1985-01-02, so 443 CL dates carry `f01`+`f03` and nothing else. That
is why `M1-M3` has ~6,200 more rows project-wide than any other leg — a real gap in the
source, not a bug in the pivot.

### Live result (2026-09-09)

89 `curve_settles` rows (LCO, 89 contracts, the single 2026-09-04 snapshot date) and
132,546 `spreads` rows (CL 49,745 · HO 41,370 · HU 18,200 · RB 23,231, spanning
1980-01-02 → 2024-04-05). Running it twice left both table counts identical while adding
a second `publish_log` row per table — Spec 32 §8's idempotency criterion, verified
against the real database rather than assumed.

## yfinance front month — the only current futures price this project has (2026-09-09)

`pipelines/futures/pull_yfinance.py` + `yfinance_front.py`. Added because every other
real futures source here had stopped: EIA's `petroleum/pri/fut` was discontinued
**2024-04-05**, the Barchart curve is a single reconstructed 2026-09-04 snapshot, and
IBKR needs a Gateway nobody runs. The lake therefore held **no current futures price at
all** — a gap that only became visible when Spec 32's `as_of` fix made
`serving.spreads` report itself as 17 months stale.

### `.close`, not `.settle` — measured, not assumed

Yahoo publishes a daily bar whose close is the **last trade**, which is nearly but not
actually the exchange **settlement**. Measured live 2026-09-09 against the 5,915
overlapping days of this lake's own `fut.cl.f01.settle` (EIA, 2000-08-23 → 2024-04-05):

| Agreement | Result |
|---|---|
| Exactly equal | 215 days, **3.6%** |
| Within 1 cent | **96.4%** |
| Differ by > 10 cents | 29 days, 0.49% |
| Mean absolute difference | **0.27 cents** |
| Worst day | **$1.50**, 2001-09-14 |

That worst day is the week the market reopened after 11 September — precisely the kind of
disorderly session where a last trade and a settlement part company. So these are two
different quantities. Series ids are **`fut.<root>.f01.close`** with `source="yfinance"`;
writing them as `.settle` would have put two conflicting values under the same
`(series_id, ts)` across 24 overlapping years, and any reader concatenating sources would
have silently picked between them. Verified after the backfill: **0 `(series_id, ts)`
pairs carry more than one row** across `eia` + `manual` + `yfinance`.

This is the same "different things get different ids" rule that keeps `hu` and `rb`
separate roots rather than splicing them at ingestion.

### Coverage

Front month only, five roots, `--period max` backfill live-verified 2026-09-09:

| Series | Symbol | Rows | Span |
|---|---|---|---|
| `fut.cl.f01.close` | `CL=F` | 6,539 | 2000-08-23 → current |
| `fut.ng.f01.close` | `NG=F` | 6,536 | 2000-08-30 → current |
| `fut.ho.f01.close` | `HO=F` | 6,533 | 2000-09-01 → current |
| `fut.rb.f01.close` | `RB=F` | 6,494 | 2000-11-01 → current |
| `fut.lco.f01.close` | `BZ=F` | 4,757 | 2007-07-30 → current |

30,859 rows total. **Not a curve source**: Yahoo's individual contract symbols
(`CLZ26.NYM`) are patchy and unreliable, so `serving.curve_settles`, Dec-Dec spreads, the
roll calendar and anything beyond rank 1 still need IBKR or a Barchart drop. Nothing
downstream may treat this as a curve.

Scheduled in `infra/run_scheduled.py`'s `daily` group with the default `--period 1mo`
(comfortable margin over a long weekend); `--period max` is the one-off backfill.
Idempotent — re-running the 1-month window over the existing backfill left the lake at
30,859 rows, unchanged, and the publish reads the **whole lake** rather than the pulled
window so `serving.series_long` keeps its full history.

### Caveats that matter

`yfinance` is an unofficial client for an undocumented Yahoo endpoint: no SLA, and it
breaks whenever Yahoo changes shape. Treat a failure as expected maintenance, not an
incident, and never fall back to stale numbers to paper over one. Yahoo's terms also
restrict redistribution, which is a live question for `data.kardamow.com` — these rows
are published into an anon-readable `serving.series_long`. The per-symbol pull is wrapped
in `core.failures`, so one broken symbol does not cost the other four, but a run where
every symbol failed still exits non-zero rather than reporting success.

## IBKR MCP connector — daily-bar history limit, confirmed live 2026-10-10

`get_price_history(security_type="FUT", exchange="NYMEX", step="ONE_DAY", outside_rth=false)`
on CL Dec 2026 (contract_id 296574787):

| period | result |
|---|---|
| `ONE_YEAR` | 251 bars, 2025-10-10 -> 2026-10-09 |
| `FIVE_YEARS` | **1,255 bars, 2021-10-11 -> 2026-10-09** |

`FIVE_YEARS` is the largest value the tool's own enum offers, so there is no deeper period
to test -- five years of daily bars per contract is the ceiling. Every response carries
`delayed: 600` and `source: "Last"`, which is why these are `.close` series and never
`.settle`.

Not the same as the monthly-bar limit: `step="ONE_MONTH", period="FIVE_YEARS"` on CLZ7
returned bars back to 2021-10-11 too (confirmed 2026-10-10), i.e. the five-year window is
the binding constraint, not the bar size.

**Operational consequence for any capture.** One contract at `FIVE_YEARS` daily is roughly
**70 KB of JSON**. The nearest 36 expiries across two roots is therefore on the order of
**5 MB** -- far past what any single agent should pull through its own context. A capture
must stream each response straight to disk under `data/raw/ibkr/` rather than reading it.
Responses above the tool's own result cap are auto-saved to a file by the harness, which
helps, but the cap sits between the `ONE_YEAR` and `FIVE_YEARS` sizes, so it cannot be
relied on as the mechanism.

## The IBKR MCP connector as a data source (2026-10-10)

**This is not the Gateway path.** The section at the top of this file — "No IBKR Gateway/TWS
running on this machine" — remains true and remains irrelevant to this source. All four
ports are still closed and `ibkr_preflight.py` still reports so; it tells you nothing about
the connector, which is an MCP tool available inside a Claude session and needs no Gateway,
no port and no `ib_async`.

Resolved underlying contract ids, so nobody re-derives them: `cl` = 17340715 (Light Sweet
Crude Oil, NYMEX), `lco` = 45631501 (Brent Crude Oil – Last Day, NYMEX). Futures are not
SMART-eligible — pass the contract's native `exchange` or the response comes back empty.

### Provenance: these are `.close`, never `.settle`

Every response carries `delayed: 600` and `source: "Last"`. That is last-trade data, ten
minutes delayed, not an exchange settlement. The measured difference between the two, from
this file's own yfinance section, is exactly equal on **3.6%** of 5,915 days, within a cent
on 96.4%, worst day **$1.50**. So the series are `fut.<root>.<contract>.close` with
`source="ibkr"`, and nothing may relabel them.

Open interest is **not** written. `future_open_interest` was requested on three contracts
and returned on none. Absent is not zero.

### What the capture produced, 2026-10-10

36 nearest non-expired contracts per root, five years of daily bars each. `cl` 2,172,048
bytes and `lco` 1,254,164 bytes of archived JSON under the git-ignored `data/raw/ibkr/`.
Ingested: **13,038** rows for `cl` across 35 of 36 contracts, **2,544** for `lco` across 34
of 36 — 15,582 rows in total.

### Two real defects in the source, both found by running against it

**Ragged parallel arrays, 3 of 72 contracts.** The connector returns OHLCV lists of
differing lengths: `cl` 202901 came back `time=180, open=180, high=249, low=249, close=249,
volume=231`; `lco` 202701 had `time=249` against 250 everywhere else; `lco` 202703 had
`volume=243` against 249. The first real ingest aborted both whole captures on pandas'
opaque `ValueError: All arrays must be of the same length`. Now refused per contract with a
named error, recorded as a skip, so one bad contract costs only itself.

**Duplicate price series are a symptom, not a bug.** Three pairs of contracts returned
byte-identical close series. They are 92–99% zero-volume far-dated contracts printing
carried reference prices, so the two "duplicates" are both mostly non-markets and the
liquidity gate strips them. Worth knowing before anyone reports it as a connector fault.
Note `cl` 202901's zero-volume bars carry *varying* OHLC, so they are counted `zero_volume`
rather than `stale_print` — the two reasons are not redundant.

### The limitation that matters most

`search_futures` returns only contracts **still active** unless `include_expired=true`. This
capture took the nearest 36 non-expired, so every contract that was front-month in the past
is missing. Consequences:

- **Contract-coded output is correct.** `fut.cl.z2026.close` is genuinely that contract, and
  `dec_dec_4026_4027` names both its legs.
- **Rank-based output is not, historically.** `core.curve.nearby_panel` ranks whatever is in
  the panel, so on 2026-04-02 it calls `x2026` (expiry 2026-10-20) the front month at 73.16
  when the real front expired in May 2026 and was never captured.

Measured against the lake's independent yfinance front month: 294 overlapping days, max
absolute difference **38.38**, median 2.61, 0.3% within a cent. Two last-trade series for the
same instrument do not disagree like that — they are not the same instrument.

**A capture that wants genuine historical ranks must pass `include_expired=true`.** That is
the real fix and it was not done here.

### A namespace hazard, recorded because it did not bite

`pipelines/derived/curve_ranks.py` (EIA rank series) and `pipelines/derived/curve.py` (the
contract panel) write **the same series ids** — `derived.spread.<root>.s12` and siblings —
from different inputs. They do not collide today only because EIA's route was discontinued
at 2024-04-05 while this capture begins 2024-04-17: zero overlapping timestamps, verified by
grouping on `revision_date`. If EIA data ever extended forward, or a capture reached further
back, `write_ts_long`'s `(series_id, ts)` de-dup would let one path silently overwrite the
other.

