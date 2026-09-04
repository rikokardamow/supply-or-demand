# Spec 27 — Trade Journal, Playbook Library & Kardamow Validation Ledger

**Sources:** Johnson *40 Classic Crude Oil Trades* (Routledge 2022; chapter list below); Newman (2015 Cushing super-contango, Apr-2020, 2022 financing constraints, OPEC+ psychology); Imsirovic (benchmark squeezes); Bouchouev (Apr-2020 storage boundary; synthetic storage — trade 39). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Three linked stores: (A) trade journal with structured post-trade review, (B) playbook of case cards, (C) Kardamow article validation & conviction ledger. Exposes `log_signal_trade()` (called by Specs 20/21/24/25/26 when a strategy flips) and `open_gauges()`. Page `27_journal.py`.

## Storage
A new current-state dataset family in `core/schemas.py` / `core/storage.py` — `journal`, `playbook`, `kardamow_ledger`, `ledger_audit` — following Spec 15's precedent (`SANCTIONS_SCHEMA`: a state table, not `_write_partitioned`). Ledger rows immutable once `status` leaves Open except `post_mortem`; every edit appended to `ledger_audit`. Fields:
- `journal`: opened, closed, book, strategy_id, signal_spec, instrument, side, qty, entry, exit, target, stop, thesis, regime_state, util_decile, cot_pct, vol_target, pnl_total, pnl_directional, pnl_carry, pnl_vol, slippage_vs_tas, outcome, lesson, playbook_ref, kardamow_ref.
- `playbook`: title, contributor, category, era, setup, mechanism, expression, risk, lesson, tags (list — the `events.tags` precedent), source, page_ref.
- `kardamow_ledger`: title, published, type, url, rubric_grade, mechanism, trigger_x, outcome_y, channel_z, level, horizon_days, instruments (list), entry_marks (json), status, resolved, outcome_marks (json), hypothetical_pnl, s_trigger, s_channel, s_magnitude, s_reflexive, conviction, post_mortem, regime_state, util_decile, beat, mechanism_family, series_arc.

## Sessions

### Session A — schemas, storage, playbook seed
`core/journal.py` schema + read/write; `pipelines/playbook/seed.py` seeds Johnson's 40 chapters (title, contributor, category, source, page_ref only — **no book text**) plus six supplementary cards (2015 Cushing super-contango; Apr-2020 negative WTI; Mar-2022 backwardation & financing; Mar-2020 Saudi–Russia price war; Metallgesellschaft stack-and-roll; Brent squeezes). Johnson's list, by category:
Arbitrage — 1 Night Flight To Siberia (Colin Bryce); 2 A Sweet Deal (Philippe Khoury); 3 Where Physical Meets Paper (Kurt Chapman); 4 A False Arbitrage (Adi Imsirovic); 5 A Russian Arbitrage Strategy (Trym Nordhus); 6 Leveraging Local Knowledge (Ralf-Dieter Poth); 7 Finding The Global Optimal (Manosh Saha). Macro/micro & geopolitics — 8 Calling A Collapse (Eric Rubenstein); 9 Learning From Misfortune (Cui Zhenchu); 10 Facing A Force Majeure (Anne Devlin); 11 Trading The Micro Structure (Sylvia Low); 12 Financing Oil Traders (Philippe Cohen); 13 Starting From 'Why Not' (Alessandro Liberati). Spot vs term — 14 Publish And Circulate (Elizabeth Bossley); 15 Bringing Indexation To Russia (Elena Lobodina); 16 Updating The NOC Model (Juan Carlos Fonnegra); 17 Flexibility Of Supply (Mohammed Minkara); 18 Turning Weakness Into Strength (Michael Dugdale); 19 The Value Of Persistence (Geena Malkani). Logistics & storage — 20 Preserving Pipeline Economics (John Krus); 21 A U.S. Pipeline Frenzy (Anne Summers); 22 Finding Interesting Niches (Michael Hacking); 23 Smoothing Logistics (Chris Del Vecchio); 24 Trading Floating Storage (Daphne Teo); 25 Trading Around Strategic Storage (Justus van der Spuy). New crude grades — 26 Marketing The First Brent (Richard Johnstone); 27 Flexibility Plays (Rajaraman Jayaraman); 28 Refining The First Norwegian Oil (Bridie Tobin); 29 Marketing A New Stream (David Jorbenaze); 30 Splitting Basrah (Thomas Andersen); 31 Asia's Shift To Sour (Andrew Dodson). Derivatives — 32 WTI Proves Itself (Thomas McMahon); 33 From Floor To Screen (Steve Roberts); 34 Bringing Brent Onscreen (Milan Kratka); 35 Trading Opaque Markets (Greg Newman); 36 Trading As A Calling Card (Gary King); 37 A Chart For Success (Kevin McCormack); 38 Trading On Behalf Of A Nation (Gerardo Rodríguez); 39 The Invention Of Synthetic Storage (Ilia Bouchouev); 40 Making A Major Shift (Richard Fullarton).
- Tests: seed has exactly 40 + 6 rows; ledger immutability enforced (editing `level` on a resolved row raises; editing `post_mortem` writes audit).
- DoD: [ ] schemas + storage, [ ] seed, [ ] tests.

### Session B — journal logic
```python
def log_signal_trade(strategy_id, spec, instrument, side, qty, entry, thesis, as_of) -> int   # snapshots regime_state, util_decile, cot_pct from the lake at as_of
def close_trade(id, exit, closed, outcome, lesson) -> None    # pnl split: directional (Δf01_adj×qty), carry (roll yield accrued), vol (options MTM residual), slippage_vs_tas
def review_form(id) -> dict
def journal_stats(filters) -> DataFrame                        # hit rate, avg win/loss, Sharpe by spec/strategy/regime (reuse core.backtest.fractionate)
```
- Tests: pnl parts sum to total ±1e-6; snapshot at `as_of`, not latest.
- DoD: [ ] functions wired into Spec 21's daily positions step (a flip logs a trade), [ ] tests.

### Session C — Kardamow ledger (`core/ledger.py`)
```python
def parse_gauge(close_text) -> dict            # trigger_x, outcome_y, channel_z, level, horizon_days, instruments; 'unparseable' blocks the publish flag
def open_gauge(article_meta, gauge, as_of) -> int      # snapshots entry_marks
def distance_to_trigger(row, as_of) -> float           # 0..1
def resolve(id, status, as_of, notes) -> None          # Open / Validated / Falsified / Ambiguous / Expired-untested; snapshots outcome_marks, hypothetical_pnl
def score(id, s_trigger, s_channel, s_magnitude, s_reflexive) -> int   # 0–25 each; right Y via wrong Z caps s_channel at 10; conviction = sum
def hit_rate(by) -> DataFrame                          # excludes Expired-untested from the denominator
def calibration(rubric_grade_bins, outcome) -> DataFrame
def thesis_drift(series_arc) -> DataFrame              # flags goalpost moves across a serialised arc
def followup_candidates(as_of) -> DataFrame            # resolved in last 7d → stub for the one-liner/X skills; falsifications with equal prominence
```
- Tests: `parse_gauge("If Cushing falls below 20 mb, the M1–M2 spread trades above $2 within 60 days through storage-boundary repricing")` → trigger 'Cushing < 20 mb', outcome 'M1–M2 > $2', channel 'storage-boundary', horizon 60; channel cap; denominator rule.
- DoD: [ ] functions, [ ] tests.

### Session D — page `27_journal.py`
Streamlit forms (journal entry, review, gauge open/resolve/score). Theme additions: `attribution_stack_chart`, `progress_bar_table` (open gauges: distance-to-trigger, days vs horizon, live marks), `calibration_curve_chart`, `drift_timeline_chart`. Views: journal table + attribution + hit-rate heatmap (Spec 21 fractionation on journal P&L); playbook browser (category tabs, tag search, linked journal entries); open gauges board; conviction analytics by beat/type/mechanism family/regime/util decile; calibration; thesis drift; accountability feed.
- DoD: [ ] page live, [ ] a real ledger row opened from a published Kardamow piece and its entry marks verified against the lake.

## Definition of Done (spec)
- [ ] Sessions A–D. [ ] First ten archive pieces parsed into the ledger by hand (calibrates the parser before any auto-drafting). [ ] Index + CHANGELOG.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/27_journal-playbook-kardamow.md and core/schemas.py (SANCTIONS_SCHEMA precedent). Plan Session A: the four state-table schemas and storage functions, the playbook seed with no book text, tests.
