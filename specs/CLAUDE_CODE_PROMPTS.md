# Claude Code Prompts — Specs 34–40

One prompt = one Claude Code session. Paste the block, let it plan, approve, let it build,
end green. Never start a session you can't finish inside the time block.

---

## Before session 0 — on your Windows machine (15 min, no Claude Code)

1. Copy the seven files `34_*.md` … `40_*.md` into `supply-or-demand/specs/`.
2. IBKR paper account: log in to Client Portal → Settings → Paper Trading Account → enable
   **sharing market data with the paper account** (otherwise paper sees no prices).
3. Install **IB Gateway** (stable). Log in with the **paper** credentials.
4. Gateway → Configure → Settings → API → Settings:
   - Enable ActiveX and Socket Clients: **on**
   - Socket port: **4002**
   - Trusted IPs: **127.0.0.1** only
   - **Read-Only API: on** (leave it on until Spec 34 Session D)
5. In `.env`: `IBKR_PORT=4002`, `IBKR_HOST=127.0.0.1`, `IBKR_CLIENT_ID=1`. Leave
   `FUTURES_SOURCE=manual` for now — Session 34-B switches it.
6. Get a free TCMB EVDS API key (needed for Spec 40 only) — can wait.

---

## Session 0 — housekeeping (~30 min)

```
Read CLAUDE.md and specs/00_INDEX.md. I have added seven new specs: specs/34_ibkr-live-connection.md,
35_ibkr-option-snapshots.md, 36_noaa-hurricanes-refinery-risk.md, 37_ice-cot.md,
38_funding-rates.md, 39_carbon-eua.md, 40_em-sovereign-oil-beta.md. Read each one.

Do three things only, in plan mode first:
1. Add a "Specs 34–40 — Live trading connections" section to specs/00_INDEX.md in the same
   table format as Specs 29–33: Spec, Title, Status ("not started"), New source?, Depends on.
   Add the dependency line: 34 → 35 → (22, 24); 34 → 36-C, 39, 40-B/C; 37, 38 independent.
2. Check each new spec against the real repo — any function, file, series ID or schema it
   names that does not exist or is named differently. List mismatches; fix the spec text, not
   the code. Do not build anything.
3. Commit: "docs(specs): add Specs 34–40 live trading connections".
End green.
```

---

## Session 1 — Spec 34-A: IBKR connect and symbol discovery (~1.5 h)
*IB Gateway paper must be running and logged in.*

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md, specs/00_TRADING_CONVENTIONS.md,
specs/34_ibkr-live-connection.md and pipelines/futures/CLAUDE.md.
Execute Spec 34 Session A exactly as written. Plan first, then implement.
IB Gateway (paper, port 4002) is running now. Start by running
python -m pipelines.futures.ibkr_preflight and show me the result before anything else.
Do not guess any IBKR symbol or exchange code — discover every one live and record failures.
End green: uv run pytest, uv run ruff check ., uv run mypy core pipelines infra.
Tick the DoD boxes with the verification actually performed, update CHANGELOG and commit
as "feat(futures): Spec 34 Session A -- live IBKR connection and symbol mapping".
```

## Session 2 — Spec 35-A: option snapshots (start the history clock) (~2.5 h)

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md, specs/00_TRADING_CONVENTIONS.md,
specs/24_volatility-options.md and specs/35_ibkr-option-snapshots.md.
Execute Spec 35 Session A exactly as written. Plan first, then implement.
Verify live which option roots are entitled and whether IBKR returns IV and greeks before
writing any pull code. Vendor IV and computed IV must never share a series ID.
End green, tick DoD with real verification, CHANGELOG, commit
"feat(options): Spec 35 Session A -- daily option-chain snapshots".
```

## Session 3 — Spec 34-B: live settles and backfill (~2 h)

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md, specs/00_TRADING_CONVENTIONS.md,
specs/34_ibkr-live-connection.md and pipelines/futures/CLAUDE.md.
Execute Spec 34 Session B exactly as written. Plan first, then implement.
Switch FUTURES_SOURCE=ibkr only after the plan is approved. Respect IBKR pacing limits.
Cross-check one CL and one Brent settle against the exchange's published settlement and
record both numbers in the spec. End green, tick DoD, CHANGELOG, commit
"feat(futures): Spec 34 Session B -- live IBKR settlements and backfill".
```

## Session 4 — Spec 35-B: schedule snapshots + first smile (~2 h)

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md and specs/35_ibkr-option-snapshots.md.
Execute Spec 35 Session B exactly as written. Plan first, then implement.
Register the snapshot at the fixed time chosen in Session A. Render the CL smile card in the
browser on real data and show me a screenshot. End green, tick DoD, CHANGELOG, commit.
```

## Session 5 — Spec 38 (A then B): funding rates (~2.5 h, quick win)

```
Read CLAUDE.md, pipelines/macro/CLAUDE.md, specs/14_analytics-layer.md and
specs/38_funding-rates.md. Execute Spec 38 Session A, then Session B, exactly as written.
Plan first, then implement. Verify every FRED and ECB series ID live — none guessed.
The existing Spec 14 SOFR-replacement test must pass on the real series.
The carry_cost test must return exactly 250,000 for $100m at 5.00% ACT/360 over 18 days.
End green, tick DoD, CHANGELOG, commit.
```

## Session 6 — Spec 37-A: ICE COT pipeline (~2 h)

```
Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/19_fundamentals-physical.md,
pipelines/cftc/CLAUDE.md and specs/37_ice-cot.md.
Execute Spec 37 Session A exactly as written. Plan first, then implement.
Verify the ICE report formats per contract before mapping any category; where an ICE
category has no CFTC equivalent, say so in the mapping table rather than forcing it.
End green, tick DoD, CHANGELOG, commit.
```

## Session 7 — Spec 37-B: wire into positioning (~1.5 h)

```
Read CLAUDE.md, specs/19_fundamentals-physical.md and specs/37_ice-cot.md.
Execute Spec 37 Session B exactly as written. Plan first, then implement. End green, commit.
```

## Sessions 8–10 — Spec 36 A, B, C: hurricanes and refinery risk (~6 h total)

```
Read CLAUDE.md, specs/20_refining-crack-vecm.md and specs/36_noaa-hurricanes-refinery-risk.md.
Execute Spec 36 Session <A|B|C> exactly as written. Plan first, then implement.
Verify every NOAA and EIA source live and record URLs and quirks in pipelines/noaa/CLAUDE.md.
Never geocode a refinery by name guesswork. End green, tick DoD, CHANGELOG, commit.
```

## Session 11 — Spec 34-C: read-only account state (~1.5 h)

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md and specs/34_ibkr-live-connection.md.
Execute Spec 34 Session C exactly as written. Plan first, then implement.
The paper-only guard (port 7497/4002 AND account ID starting DU) is mandatory and tested.
Account IDs must be redacted everywhere. No order code in this session. End green, commit.
```

## Session 12 — Spec 34-D: paper order adapter (~2 h)
*Turn Gateway's Read-Only API **off** before this session — paper account only.*

```
Read CLAUDE.md, specs/TRADING_LAYER_RUNBOOK.md, specs/27_journal-playbook-kardamow.md and
specs/34_ibkr-live-connection.md. Execute Spec 34 Session D exactly as written.
Plan first, then implement. Dry-run is the default. After tests pass, place exactly one
1-lot paper order that I approve in chat, read its fill back into book_fills, and show me
the row. End green, commit.
```

## Sessions 13–14 — Spec 39 A, B: carbon and switching price

```
Read CLAUDE.md, specs/04_entsoe-eu-power.md, specs/14_analytics-layer.md and
specs/39_carbon-eua.md. Execute Spec 39 Session <A|B> exactly as written.
Plan first, then implement. Never substitute a US coal series for API2 — missing API2
renders NO-DATA. End green, tick DoD, CHANGELOG, commit.
```

## Sessions 15–17 — Spec 40 A, B, C: EM sovereign oil-beta

```
Read CLAUDE.md, specs/10_macro-fx.md and specs/40_em-sovereign-oil-beta.md.
Execute Spec 40 Session <A|B|C> exactly as written. Plan first, then implement.
No series may be presented as CDS. Rolling beta must pass a look-ahead shift test.
End green, tick DoD, CHANGELOG, commit.
```

## Then — Spec 11 Session B: AIS history (already specced)

```
Read CLAUDE.md, specs/11_ais-vessels.md and pipelines/ais/CLAUDE.md.
Execute Spec 11 Session B exactly as written: the vessel_positions history table that the
compactor currently discards. Plan first, then implement. End green, commit.
```

---

### Order and why
1. **34-A → 35-A first.** Option history only starts the day snapshots run.
2. **34-B, 35-B** — live curves, scheduled surface.
3. **38, 37** — small free pulls, quick wins between bigger sessions.
4. **36** — independent of IBKR for A–B; good weekend block.
5. **34-C/D** — the paper book becomes real; Specs 22 and 27 follow from here.
6. **39, 40, 11-B** — as time allows.
