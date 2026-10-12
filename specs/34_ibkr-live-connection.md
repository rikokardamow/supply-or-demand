# Spec 34 — IBKR Live Connection (paper account)

**Est. 6–8 h (four sessions) · Prereq: Spec 18 (built — `pipelines/futures/client.py::IBKRClient`
exists, fixture-tested, never run live). Blocks Specs 35, 22, 24, 26 and 27's live book.
Runs on Riko's Windows machine only — a cloud sandbox cannot reach a local Gateway.**

## Objective & alpha question

Every futures number in the lake today is a yfinance front month, an EIA rank 1–4 history that
stops in 2024, or a manual Barchart drop. The IBKR client was built in Spec 18 and has never
connected: every session recorded "all four ports closed" by hand, and `ibkr_preflight.py`
was written to make that check reproducible.

Question: *can the lake hold an exchange-sourced, full-curve, daily settlement for every root in
`contract_specs.csv` — and can a paper book read its own positions and P&L back from the broker
rather than from a spreadsheet?* Until it can, Specs 22, 24, 26 and 27 have nothing live to run on.

## What is confirmed, and what Session A must verify

**Confirmed** (repo state, 2026-10-12):
- `IBKRClient` connects with `ib_async.IB().connect(host, port, clientId, timeout=45)`.
- `FUTURES_SOURCE`, `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID` are already in `.env.example`.
- `ibkr_preflight.py` checks ports 7497 / 7496 / 4002 / 4001.
- Contract roots: `cl, rb, ho, ng` (NYMEX), `lco, g, tfm` (ICE). Conventions also list `nbp`, `jkm`.

**Not confirmed — mandatory first step of Session A:**
- **Symbol mapping.** `list_contracts` builds `Future(symbol=root.upper(), exchange=...)`. That
  works for `CL` on NYMEX, but IBKR's own symbols for ICE Brent, ICE gasoil, TTF, NBP and JKM
  are not the lake root uppercased, and the ICE exchange code IBKR uses is not necessarily the
  `ICE` written in `contract_specs.csv`. Discover each live with `reqMatchingSymbols` and
  `reqContractDetails`; **do not guess a symbol or exchange code**. Add `ib_symbol` and
  `ib_exchange` columns to `contract_specs.csv` and record every outcome, including roots that
  return nothing, in `pipelines/futures/CLAUDE.md`.
- **Market data entitlement.** Which roots return settlements on the paper account with the
  current subscriptions. A root with no entitlement renders NO-DATA with the reason — never a
  substituted series.
- Whether paper-account historical bars are permitted to share the live account's market data
  subscriptions (an account-portal setting). Record what was actually observed.

## Hard safety rule — paper only

Any code that reads account state or places orders must refuse to run unless **both** hold:
1. the connected port is 7497 or 4002 (paper), and
2. the managed account ID returned by `ib.managedAccounts()` begins with `DU` (IBKR's paper prefix).

On failure it raises with the reason and exits non-zero. There is no flag that disables this
check, and no live-port code path exists in this repo. A test proves 7496 / 4001 and a non-`DU`
account are both refused.

## Data model — no new schema for settlements

Settlements already fit `ts_long` via `pipelines/futures/to_ts_long.py`:
`fut.<root>.<contract>.settle`, four-digit years in anything new (`z2026`), never a code matching
`looks_like_rank_code`. `source="ibkr"`, `revision_date` = ingestion time.

Account state (Session C) is **not** market data and does not go in `ts_long`. Write to a new
lake table `book_positions` (`asof, account, con_id, root, contract, qty, avg_cost, mark,
unrealised_pnl, realised_pnl, source`) and `book_fills` (`exec_id, time, con_id, side, qty,
price, commission, order_ref`). Add both to `core/schemas.py` with a migration note. Account IDs
are treated as secrets: redacted via `core.failures.redact` in every exception and log line.

## Sessions

### Session A — connect, preflight green, symbol discovery (~1.5 h)

> Read `CLAUDE.md`, `specs/TRADING_LAYER_RUNBOOK.md`, `specs/00_TRADING_CONVENTIONS.md`,
> `specs/34_ibkr-live-connection.md`, `pipelines/futures/CLAUDE.md`. With IB Gateway (paper)
> running, run `python -m pipelines.futures.ibkr_preflight` until green. Walk every root in
> `contract_specs.csv` plus `nbp` and `jkm` live via `reqMatchingSymbols` /
> `reqContractDetails`; add `ib_symbol`, `ib_exchange` columns; record every outcome. Fix
> `IBKRClient.list_contracts` to use the mapped symbol. Fixture tests for the mapping.

### Session B — live daily settles and backfill (~2 h)

> Switch `FUTURES_SOURCE=ibkr`. Pull daily settlements for every entitled root, full listed
> curve. Backfill as far as IBKR historical bars allow, respecting pacing limits (sleep and
> resume, never hammer). Cross-check: one CL and one Brent front-month settle against the
> exchange's published settlement for the same date — record both numbers. Register the daily
> pull in `infra/run_scheduled.py` after the US settlement window. Confirm a `0.35` spread reads
> back as `0.35` (the existing float64 regression test must still pass on IBKR data).

### Session C — read-only account state (~1.5 h)

> Build `pipelines/ibkr_account/` (`/new-pipeline ibkr_account`): positions, fills and account
> P&L from the paper account into `book_positions` / `book_fills`. Paper-only guard per this
> spec, with tests. Daily snapshot entrypoint registered in the scheduler. No order code in this
> session.

### Session D — paper order adapter (~2 h)

> Build `core/execution.py` (pure: order intent → validated order object, limit checks) and
> `pipelines/ibkr_account/orders.py` (the only module that calls `placeOrder`). Order intents
> come from a CSV drop or a Spec 21/27 signal — never typed ad hoc. Every order carries an
> `order_ref` linking it to a journal entry ID (Spec 27). Pre-trade checks: root entitled,
> gross notional and per-root contract limits from a config file, paper-only guard. A dry-run
> mode prints the order and places nothing; it is the default.

## Acceptance criteria

- [ ] Preflight green on a real Gateway; outcome recorded with date.
- [ ] Every root mapped or explicitly recorded as unavailable — none guessed.
- [ ] Daily IBKR settles idempotent (two runs → zero duplicates); cross-check numbers recorded.
- [ ] Paper-only guard tested against live ports and non-`DU` accounts; no bypass exists.
- [ ] Account IDs never appear unredacted in logs, exceptions or the lake's `source` column.
- [ ] Order adapter defaults to dry-run; one real paper order placed and its fill read back.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
