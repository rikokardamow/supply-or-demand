# Design — IBKR curve ingestion via the MCP connector

**Date:** 2026-10-10
**Status:** approved design, not yet planned
**Branch:** `spec/ibkr-curve`
**Surface:** `pipelines/futures/` (two new modules), one function in `pipelines/derived/curve.py`
**Does not touch:** `apps/dashboard/`, `pipelines/futures/yfinance_front.py`,
`pipelines/futures/eia_futures.py`, `pipelines/futures/publish_curve.py`, `core/curve.py`

## Why

`specs/TRADING_LAYER_RUNBOOK.md` §4 states the blocker plainly: *"Spec 18 Session A is the
gate. Nothing in the lake holds the futures curve today, and Specs 18, 20, 21 and 24 cannot
run without it."* What the lake actually holds for `fut.*` is three dead ends:

| Source | Shape | Why it does not close the gap |
|---|---|---|
| `eia_futures.py` | ranks 1–4 | the route is discontinued; it stops at 2024-04-05 |
| `barchart_curve.py` | 89-month Brent curve | a single date, 2026-09-04, reconstructed from a spreads export |
| `pull_yfinance.py` | front month only | rank 1 and nothing beyond it |

Rank 2 and beyond has never existed as a real, current series. Every session for a month
recorded the same finding: all four IBKR Gateway ports closed on this machine
(`pipelines/futures/ibkr_preflight.py` makes that check reproducible).

On 2026-10-10 the IBKR **MCP connector** was found to serve futures data read-only, with no
Gateway. Verified live that day, delayed quotes:

| Contract | Month | Last | Bid/Ask | Volume |
|---|---|---|---|---|
| CL | Nov 2026 | 91.66 | 91.64 / 91.67 | 202,301 |
| CL | Dec 2026 | 90.80 | 90.80 / 90.83 | 148,318 |
| BZ | Dec 2026 | 104.43 | 104.39 / 104.44 | 26,251 |

Ladders are deep: ~130 CL expiries to Dec 2036, ~90 BZ expiries to Mar 2034. Per-contract
daily and monthly history is available — `CLZ7` returned monthly bars back to 2021-10-11 —
so a *historical* curve panel is reconstructable, not merely today's snapshot.

This also bears directly on Spec 20. Its model card records `oos_status = fail` (Theil U
1.0725, worse than a random walk) and attributes it to the crack legs being **spot, not
futures**, with the instruction to revisit once Spec 18 ingests real settlements.

## The constraint that shapes everything

The connector is an MCP tool available inside an AI-assistant session. It is **not importable from
Python**. `infra/run_scheduled.py` cannot call it — not with a credential, not with a flag.
The fetch half only runs when an agent session runs. The design is therefore split: an
agent-side capture that archives raw responses, and an ordinary Python pipeline that parses
the archive and writes the lake.

## Goal

The lake holds a real, current, multi-contract curve for `cl` and `lco`, honestly labelled,
with illiquid stale prints excluded rather than ingested — and `pipelines/derived/curve.py`
produces genuine spreads, convexity, regime and Dec–Dec from it.

## Non-goals

- No rank series are written, so `pipelines/derived/systematic.py` is untouched and Spec 21's
  `CARRY_1_13` and `FWD_SPREAD_MR` stay skipped. See § Scope.
- No Supabase publishing. `publish_curve.py`'s regexes require a `.settle` suffix and are
  unchanged; nothing is hosted, by the owner's decision of 2026-10-10.
- No replacement of `pull_yfinance.py`. See § Other sources.
- No scheduler entry. The fetch cannot run headless.
- Roots beyond `cl` and `lco`. `rb`/`ho`/`ng` are plausible on NYMEX but unproven here;
  `g` (ICE gasoil) and `tfm` (TTF) are ICE and have not been checked at all.

## Scope, decided with the owner

This build feeds `contract_panel_for` in `pipelines/derived/curve.py` only. It deliberately
does **not** write rank series.

Spec 21's two skipped strategies need ranks 7 and 13, which the EIA source could never supply
(it publishes 1–4). Supplying them in the same change that introduces a new data source would
make any movement in results unattributable — new data, or new inputs? Spec 21's recorded
findings (Bouchouev's inventory-predictability claim not reproducing; `SHORT_SPREAD_STATIC`
missing at −0.01 against a published IR of 0.50) would become unreadable. Land the data,
confirm the curve is sane, then un-skip those strategies as a separate change with its own
before-and-after.

## Architecture

### Capture — an agent-side ritual, documented rather than coded

Per root, inside a session:

1. `search_contracts(root)` gives `underlying_contract_id`. Already resolved, recorded here so
   it need not be re-derived: `cl` = 17340715 (Light Sweet Crude Oil, NYMEX), `lco` = 45631501
   (Brent Crude Oil – Last Day, NYMEX).
2. `search_futures(underlying_contract_id)` gives the ladder. Results are **not** in expiry
   order; sort by `contract_month` ascending and take the nearest 36 non-expired.
3. Per contract, `get_price_history` with `security_type="FUT"`, `exchange="NYMEX"`,
   `step="ONE_DAY"`, `outside_rth=false`. The native `exchange` is mandatory — futures are not
   SMART-eligible and omitting it returns nothing at all.

`exchange` and `contract_id` come from the ladder row verbatim.

### The raw envelope

One file per root per capture date, archived under the already-ignored `data/raw/`:

```
data/raw/ibkr/<root>-<YYYYMMDD>.json
  { captured_at, root, ibkr_underlying_contract_id, exchange,
    delayed_seconds, top_status, price_source,
    ladder:  [ { contract_id, contract_month, last_trading_date } ],
    history: { "<contract_id>": <verbatim get_price_history response> } }
```

Archiving raw follows this project's own precedent three times over: `data/raw/opec/*.xlsx`,
`data/raw/baker_hughes/*.xlsx`, `data/raw/ais/**/*.jsonl.gz`. It buys two things a direct
write cannot: a parser bug can be fixed and the archive re-parsed without spending the call
budget again, and the parser is testable against a committed fixture — which matters more than
usual here, because **no HTTP leaves Python, so vcrpy cassettes are impossible**.

The provenance fields are not decoration. `top_status` was `FROZEN_DELAYED`, and the history
header carried a 600-second delay and a `Last` price source on every response; those facts
must travel with the data.

The ladder's `symbol` field is deliberately **not** stored. The tool's own documentation says
it must not be surfaced, and it is not needed: the contract code is derived from
`contract_month`.

### Ingest

- `pipelines/futures/ibkr_curve.py` — pure parse and transform functions, no I/O.
- `pipelines/futures/pull_ibkr_curve.py` — entrypoint; reads the archive, writes the lake.

No new package: `pipelines/futures/` already holds `client.py`, `eia_futures.py`,
`barchart_curve.py`, `yfinance_front.py`, `to_ts_long.py`, `series_meta.py` and
`publish_curve.py`, so these are two more siblings. `00_TRADING_CONVENTIONS.md` forbids new
package trees.

### Series written

| Output | Value |
|---|---|
| `fut.<root>.<contract>.close` | the daily bar's close, `source="ibkr"` |
| `fut.<root>.<contract>.volume` | the bar's real volume |
| `.oi` | **not written.** Open interest was requested on three contracts and returned on none. `None`, never `0.0` |
| `series_meta` row | `expiry` from `last_trading_date`; `tick_size`/`contract_unit`/`currency` from the existing `contract_specs.csv`; `roll_rule="5bd_before_expiry"`; `source="ibkr"` |

**`.close`, not `.settle`, and this is not a detail.** The history response reports its price
source as `Last` — last trade, not exchange settlement. `pipelines/futures/NOTES.md` already
records what that difference is worth, measured over 5,915 overlapping days against real EIA
settlements: exactly equal on **3.6%** of days, within a cent on 96.4%, worst day **$1.50**
(2001-09-14, the week the market reopened after 11 September). Writing last-trade data under
`.settle` is the error this project already paid for once and named.

A related flag, not a finding, for whoever next touches the Gateway path:
`IBKRClient.get_settles` requests `whatToShow="TRADES"`, which may also be last-trade rather
than settlement. Unverified against IB's documentation; worth checking before that path is
trusted.

**Contract codes** derive from `contract_month`: `202612` becomes month letter `z` plus a
four-digit year, `z2026`. Month letters are the standard exchange set, `F G H J K M N Q U V X
Z` for January to December. Four-digit years cannot collide with the `f01..f36` rank namespace
by construction, and the parser asserts it anyway via `looks_like_rank_code` — the single
definition in `client.py`, whose docstring already names IBKR as a caller that must clear it.

**`unit`** is built exactly as `to_ts_long.py` does, currency over contract unit, so these rows
carry the same convention as the existing contract-coded rows rather than a second one.

**`revision_date`** is the envelope's `captured_at`. Re-parsing an archive is therefore
idempotent under `write_ts_long`'s `(series_id, ts)` de-dup, and a later re-capture supersedes
an earlier one.

One welcome side effect: `series_meta`'s de-dup key is `(root, contract)` without `source`, so
IBKR's **real** expiries overwrite Barchart's, which were published as NULL because the
reconstruction carried none.

### The liquidity gate

`CLZ7`'s 2021-12 bar reads `57.31 / 57.31 / 57.31 / 57.31` on **volume 0**. That is a carried
reference price, not a market, and once in the lake it is indistinguishable from a real
observation. A bar is rejected when any of:

1. `volume == 0`;
2. open, high, low and close are all equal with no volume — the stale-print signature, named
   separately so a test asserts it against a real shape rather than an invented one;
3. `close` is null or absent;
4. `close <= 0`, or `open == 0.0` (observed live on CL Nov's snapshot).

Rejections are **counted and reported per contract**, in the same idiom the EIA pipelines
already use (`"dropped N row(s) with no value"`). Never filled, never zeroed. This is
`00_TRADING_CONVENTIONS.md`'s "degenerate inputs fail loudly" rule, which that file introduces
with four real instances from Spec 21 alone.

The gate **left-trims** each contract rather than discarding it: a far-dated contract's life
runs illiquid then liquid as it approaches the front, so the liquid tail is kept and the dead
beginning dropped. If a root ends with fewer than two liquid contracts, `derived/curve.py`
already prints `"not enough contracts for a curve yet"` and writes nothing — existing
behaviour, no fabrication required.

### The one existing-code change

`contract_panel_for(root, meta)` in `pipelines/derived/curve.py` becomes suffix-aware. It
reads both `.settle` and `.close` and, **per contract**, uses settle if that contract has any
settle rows and close otherwise.

Per contract, not per row. Blending two different quantities inside one column is the same
class of defect as Spec 32's `vs_median_pct` bug, where the function's inputs were not what it
assumed, every unit test passed, and the published output read +11,462%.

The return arity stays `(contract_panel, expiries)` so `apps/dashboard/pages/18_curve.py` is
unaffected; provenance is available through a new `return_provenance=False` parameter.

## Error handling and edge cases

- `core.failures` throughout: `record_failure` per contract, `main` wrapped in
  `failure_scope("futures.pull_ibkr_curve")`. One unparseable contract must not cost the other
  35, and a run with any recorded failure still exits non-zero. Same semantics as
  `pipelines/social` and `pipelines/adanos`.
- An empty `history` entry for a contract is a **recorded skip**, not an error and not an
  empty series. Entitlement can change between captures.
- A capture is not simultaneous: contracts are fetched seconds apart, and quotes are ten
  minutes delayed. This is one reason the design uses **daily bars rather than snapshots** —
  a day's bar is a day's bar regardless of when it was pulled.
- IBKR `contract_id` values are never used as series keys. Codes derive from `contract_month`,
  so a re-issued id cannot orphan a series.
- Deliberately **absent from `infra/run_scheduled.py`**, with the reason recorded: the fetch
  half cannot run headless, and registering the parser alone would rewrite identical rows from
  an unchanged archive. `manual_physical` and `ais` are documented as unscheduled the same way.

## Testing

No cassettes, and the reason belongs in the test file: vcrpy records HTTP made from Python,
and this data never passes through Python's HTTP stack.

A committed fixture instead, following the `tests/fixtures/opec_momr/` precedent:
`tests/fixtures/futures/ibkr_curve_cl_20261010.json` — a trimmed real envelope that
**includes the zero-volume stale print**, so the gate is exercised against a real shape.

`tests/test_ibkr_curve.py`:

- contract-code derivation across all twelve month letters;
- a four-digit year never satisfying `looks_like_rank_code`;
- the gate rejecting the stale print while keeping the liquid tail;
- idempotency — parse the same envelope twice, row count flat;
- `unit` matching `to_ts_long.py`'s currency-over-contract-unit convention;
- the **float64 regression** the conventions require: a `0.35`-scale value reading back as
  `0.35` and not `0`, alongside a deliberately int64-typed sibling source in the same glob,
  mirroring the existing guard in `tests/test_storage.py`.

`tests/test_derived_curve.py` gains one case: `contract_panel_for` prefers settle over close
and does not blend them within a single contract.

## Cross-checks before the data is trusted

`00_TRADING_CONVENTIONS.md` requires at least one real number checked against an independent
source per data session. Two here:

1. **IBKR front month against the lake's `fut.cl.f01.close`** (yfinance) on overlapping dates.
   Both are last-trade, so they should agree tightly; `yfinance_front.py` already measured
   yfinance against EIA settlements, so this closes the triangle. Report maximum absolute
   difference and the share within a cent, in that same table shape.
2. **The Brent–WTI December spread.** Dec BZ at 104.43 against Dec CL at 90.80 is **$13.63**,
   wide against the usual few dollars. Verify December against December with an independent
   public quote before any `lco` row is trusted. If it is real, it is a finding worth
   recording; if it is not, something about these contracts has been misread.

Note for anyone labelling Brent from this source: `BZ` is **NYMEX Brent Last Day**, not ICE
Brent. `pipelines/cftc/NOTES.md` carries a corrected section on exactly this mistake, and the
volumes here say the same thing — 26,251 lots against WTI's 202,301. ICE Brent reports to the
FCA and is not reachable through this connector.

## Open question, to resolve before the backfill shape is fixed

The maximum `period` for a one-day bar step on a futures contract is **unknown**. The
five-year probe used monthly bars. Task 0 of the implementation plan confirms it live on one
contract. Guessing it is precisely what this project's notes repeatedly warn against.

## Other sources

- **Barchart** — the forward path retires. `barchart_curve.py` gains a pointer to this source
  but is **not** deleted: it documents a genuine reconstruction technique, validated to the
  cent against a published settlement, and it has tests. Its 89 rows stay, distinguishable by
  `source="manual"`.
- **yfinance** — untouched, and explicitly not replaced. It holds 30,859 rows of front month
  back to 2000-08-23; IBKR's per-contract history cannot reach that far, so swapping it out
  would destroy history rather than upgrade it. Its one real liability — Yahoo's
  redistribution terms against an anon-readable `serving.series_long` — lapsed when hosting
  stopped.
- **EIA ranks** — untouched. Still the rank namespace, still genuine settlements, still ending
  2024-04-05.

## Risks

- **The gate is the whole correctness story.** If it is too loose, illiquid stale prints enter
  the curve and every spread, convexity and regime value downstream inherits them while every
  test still passes. If it is too tight, the back of the curve thins out and `nearby_panel`
  has fewer ranks to work with. The fixture carrying a real stale print is the mitigation.
- **Delayed and frozen data.** Adequate for end-of-day research; not a live board. If a live
  board is ever wanted, this is not the source.
- **Entitlement may change.** A future capture could return empty; the parser must treat that
  as a recorded skip, never as an empty series written over good data.
- **The suffix change touches a load-bearing path.** `contract_panel_for` feeds page 18 and
  every `derived.*` curve series. The backwards-compatible return arity and the added test are
  the guard.

## Definition of done

- [ ] Task 0's daily-bar period limit confirmed live and recorded in `pipelines/futures/NOTES.md`
- [ ] 36 nearest `cl` and `lco` contracts captured; envelopes archived under `data/raw/ibkr/`
- [ ] Lake holds `fut.cl.*.close` and `fut.lco.*.close`; no `.oi` rows; no zero-volume bars
- [ ] `series_meta` carries real expiries for both roots
- [ ] `derived/curve.py` writes real `s12`/`s13`/`cv123`/`regime`/`dec_dec` for both roots —
      the first time `lco` has had any
- [ ] Both cross-checks performed and the numbers recorded, including a miss if it is one
- [ ] Rejection counts reported per contract
- [ ] `pytest`, `ruff check .`, `mypy core pipelines infra` all green
- [ ] `pipelines/futures/NOTES.md` records the delayed/last-trade provenance, the gate, and
      the resolved underlying contract ids
- [ ] Per the owner's standing rule, `/code-review` and `/security-review` run on the branch
      diff before it is called done
