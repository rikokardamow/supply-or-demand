# Spec 35 — IBKR Daily Option-Chain Snapshots

**Est. 4–5 h (two sessions) · Prereq: Spec 34 Sessions A–B. Feeds Spec 24 (vol surface,
event vol), Spec 22 (risk) and the crowding overlay's skew input. Start this as early as
possible: option history in this lake begins on the day the first snapshot runs.**

## Objective & alpha question

Spec 24 defines `opt.<root>.<contract>.<strike>.<c|p>.settle` but there is no source. Free
historical implied volatility for energy options does not exist at a usable depth; the only
honest route is to **collect it ourselves, daily, starting now**, so that by mid-2027 there are
six-plus months of surface history to test event-vol trades against.

Question: *how does implied vol on CL, Brent and NG price an OPEC+ meeting, an SPR release or a
Hormuz incident relative to the move that follows — and does that gap persist?* Unanswerable
without a surface history.

## What Session A must verify live

- Which option roots are entitled on the paper account: `CL` (NYMEX `LO`-family), `NG`, `RB`,
  `HO`, ICE Brent options. Use `reqSecDefOptParams` against the underlying future's `conId`.
  **Do not hard-code option trading classes** — record what the API returns.
- Whether IBKR returns model greeks (`modelGreeks`) and implied vol on the paper account with
  current subscriptions, or only bid/ask. If IV is not returned, compute it in `core/vol.py`
  (Black-76, Spec 24) from mid prices and label the series as computed, not vendor.
- Snapshot timing: pick one fixed time after the US settlement window and record it. A surface
  sampled at different times of day is not a time series.

## Scope — deliberately bounded

Per root: the next **6 listed expiries**, strikes within **±25% moneyness** of the underlying
future, calls and puts. That is the region event-vol and skew analysis uses; deep wings are
noise for a paper book and multiply pacing cost. Both bounds are config, not constants.

## Data model

Extends Spec 24's IDs; `ts_long` throughout, `source="ibkr"`:

- `opt.<root>.<contract>.<strike>.<c|p>.bid` / `.ask` / `.mid` / `.iv` / `.delta` / `.oi`
- `opt.<root>.<contract>.und` — the underlying future's price at the snapshot instant
- Strikes written without a decimal point ambiguity: `075.50` → `75p50`. One helper, one test.
- Four-digit year contract codes (`z2026`) — never a rank-colliding code.

`.iv` from IBKR and `.iv` computed in `core/vol.py` must never share an ID: the computed one is
`.iv_calc`. A test asserts both cannot be written for the same strike under the same ID.

## Sessions

### Session A — discover, pull, store (~2.5 h)

> Read `CLAUDE.md`, `specs/TRADING_LAYER_RUNBOOK.md`, `specs/00_TRADING_CONVENTIONS.md`,
> `specs/24_volatility-options.md`, `specs/35_ibkr-option-snapshots.md`. Verify entitled option
> roots and whether IV/greeks come back, live. Build `pipelines/options/` (`/new-pipeline
> options`) with `pull_snapshot.py`: chain discovery, bounded strike selection from config,
> pacing-safe market data requests, write to `ts_long`. Fixture tests on a mocked `ib_async`.
> Record every live finding in `pipelines/options/CLAUDE.md`.

### Session B — schedule, integrity, first surface (~2 h)

> Register the snapshot in `infra/run_scheduled.py` at the fixed time chosen in Session A.
> Add a lake integrity check: a snapshot with fewer than N strikes per expiry, or an
> underlying price missing, fails loudly rather than writing a thin surface. Render one card
> on a stub page: today's CL smile per expiry and ATM term structure, house style, caption
> naming the source and whether IV is vendor or computed. Cross-check one ATM IV against
> IBKR's own option chain display and record both numbers.

## Acceptance criteria

- [ ] Entitled roots and IV availability verified live and recorded, nothing assumed.
- [ ] Daily snapshot idempotent; strike/expiry bounds come from config.
- [ ] Vendor IV and computed IV never share a series ID (tested).
- [ ] Thin or partial snapshots fail loudly (`PartialFailureError`), not silently.
- [ ] First smile card renders on real data with a sourced caption.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
