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
