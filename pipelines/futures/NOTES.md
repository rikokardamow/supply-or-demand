# pipelines/futures — notes

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
