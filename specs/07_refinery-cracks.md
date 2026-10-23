# Spec 07 — Refinery Margins & Crack Spreads (Interactive Brokers via ib_async)

**Weeks 10–11 · Est. 10–14 h · Prereq: Specs 00, 01 (utilisation series), 06 (runs context).**

## Objective & alpha question
Compute 3-2-1 and diesel/gasoil cracks as the cleanest refinery-profitability signal, and
reproduce the exhibit set: dual-axis runs-vs-margins YoY, margin-vs-utilisation scatter with fitted
log curve and highlighted recent months. Question: *do current margins justify higher runs, and is
the margin move stocks-driven or utilisation-driven?*

## Data source
**`ib_async`** (v2.x, `ib-api-reloaded` — the maintained successor; `ib_insync` is dead/unmaintained,
never import it). Requires TWS or IB Gateway running locally with API enabled
(TWS paper 7497 / live 7496; Gateway 4002/4001). Delayed data is free with the IB account
(`reqMarketDataType(3)`); historical bars via `reqHistoricalData`.
Contracts (front + next month, roll by volume or 5 days pre-expiry):
- WTI `CL` (NYMEX, $/bbl) · Brent `BZ` (NYMEX) and/or ICE Brent · RBOB `RB` (NYMEX, $/gal)
- ULSD/Heating Oil `HO` (NYMEX, $/gal) · ICE Low Sulphur Gasoil `G`-style (ICE, $/tonne)
- Henry Hub `NG`; TTF if permissioned (feeds Specs 02/04 stretch).
**Fallback:** yfinance `CL=F, RB=F, HO=F, BZ=F, NG=F` for backfill only — unreliable for
continuous futures, never production.

## Data model
- Futures settles → `ts_long` (`series_id`='fut.cl.m1', `source`='ibkr').
- Computed cracks → `ts_long` (`crack.321.wti`, `crack.diesel.nwe`, `crack.rbob.wti`, `crack.ho.wti`).

## Transformations (`pipelines/ib_futures/cracks.py` — pure functions, hand-checked tests)
- **3-2-1 = (2 × RBOB × 42 + 1 × ULSD × 42 − 3 × WTI) / 3** ($/gal × 42 → $/bbl).
- Single-product cracks: RBOB×42 − WTI; ULSD×42 − WTI.
- **NW Europe diesel crack = (ICE gasoil $/t ÷ 7.45) − Brent** ($/bbl).
- YoY changes; seasonal corridors; margin-vs-utilisation join (Spec 01's `WPULEUS3`).
- Fitted curve for scatter: `y = a·ln(x) + b` via `numpy.polyfit` on ln(x).

## Visualisation spec (page `07_cracks.py`) — exhibit replication
1. **Dual-axis YoY** (Exhibit-2 style): global/US runs YoY (navy, left, mb/d) vs 3-2-1 YoY (red, right, $/bbl), correlation annotated bottom-left.
2. **Scatter + fit** (Exhibit-6 style): US 3-2-1 (x) vs utilisation % (y), grey history dots, navy dashed fitted log curve, **last 3–5 months as larger red dots**, "Red markers are <months>" note.
3. Crack seasonal corridors (3-2-1, NWE diesel).
4. Crack forward strip from the futures curve (stretch: strip chart M1–M12).

## Sessions

### Manual prep (~30 min)
Install IB Gateway, enable API, confirm delayed data. Note the port. Never store the IB password in the repo.

### Session A (weekend, 3 h) — connection + history
> Read NOTES.md, specs/07_refinery-cracks.md. Scaffold `pipelines/ib_futures/` using ib_async
> (assert at import that ib_insync is NOT installed). Config: host/port/clientId via core.settings
> (optional fields). Implement contract resolution for CL/BZ/RB/HO/NG front+second month with a
> documented roll rule, `reqMarketDataType(3)`, and `fetch_history(contract, '2 Y', '1 day')` →
> ts_long. IB calls are not cassette-testable — isolate all IB I/O in one module and unit-test
> everything downstream with fixtures. Acceptance: 2 years of CL/RB/HO daily settles in the lake.

### Session B (weekend, 3 h) — cracks + exhibits
> Implement cracks.py per the spec formulas with hand-computed test values
> (e.g. RBOB 2.40, ULSD 2.60, WTI 78 → 3-2-1 = (2·100.8 + 109.2 − 234)/3 = $25.60). Build page 07:
> dual-axis YoY chart joining Spec 01 utilisation, scatter-with-fit component in core/theme.py
> (reused later), crack corridors. Acceptance: exhibits visually match the house style; tests green.

### Session C (weekday, 1 h) — resilience + backfill
> yfinance backfill script (flagged `source='yf_backfill'`, never overwrites IB rows); graceful
> "Gateway offline" handling (pipeline skips with a logged warning, page shows data-as-of badge).

## Definition of Done
- Daily settles for ≥5 contracts; 4 crack series computing with hand-checked tests.
- Exhibit-2-style and Exhibit-6-style charts live. Gateway-offline degradation graceful.

## Stretch
- Forward crack strip; EU gasoil-vs-TTF switching economics; margin decomposition (stocks vs utilisation channels, Exhibit-9 style stacked bars).
