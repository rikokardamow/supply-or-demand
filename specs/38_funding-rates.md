# Spec 38 — Funding Rates (SOFR, €STR, term curves)

**Est. 2–3 h (two sessions) · Prereq: Spec 10 (macro, built — `pipelines/macro/fred_client.py`).
New source: ECB Data Portal. Feeds Spec 14's carry calculation, Spec 25's arb financing leg and
Spec 26's storage economics.**

## Objective & alpha question

Spec 14 already expects `fred.sofr` and holds a constant in its place, with a test asserting the
constant is replaced once the series exists. Spec 25's landed-cost arb and Spec 26's storage
valuation both need the cost of carrying a cargo or a tank, and the lake holds no money-market
rate at all — only `FEDFUNDS` monthly and Treasury yields.

Question: *how much of a contango is pure financing, and how much is storage and risk premium?*
A cargo on the water for 18 days, or gas in a cavern for five months, is a funded position. A
carry calculation without a funding rate is a fixed-income trade with the coupon missing.

## Sources

| Series | Source | Notes |
|---|---|---|
| SOFR | FRED `SOFR` via the existing `FredClient` | add to `fred_series.py`; no new client |
| SOFR term averages (30/90/180-day) | FRED — verify the exact series IDs via the FRED search API, do not guess | |
| €STR | ECB Data Portal REST API | verify the dataflow and key live; record them |
| EUR term rates (EURIBOR 3M/6M) | ECB Data Portal, or FRED if mirrored | verify; prefer the primary source |
| SONIA (for NBP carry) | Bank of England database | optional; verify access before building |

## Data model

`ts_long`. FRED series keep the existing `fred.<lowercase id>` convention (`fred.sofr`). ECB
series: `ecb.estr`, `ecb.euribor_3m`, `ecb.euribor_6m`. `unit="pct"`, never converted at ingest.
Day-count conventions (ACT/360 for SOFR and €STR, ACT/365 for SONIA) recorded in
`core/calendars.py` and used only in `core/`.

## Analytics — add to `core/macro.py`

```python
def carry_cost(notional: float, rate_pct: pd.Series, days: int, basis: int = 360) -> pd.Series
def implied_storage_premium(spread: pd.Series, funding_cost: pd.Series) -> pd.Series
```

Test: $100m at 5.00% ACT/360 for 18 days = $250,000 exactly.

## Sessions

### Session A — pulls (~1.5 h)

> Read `CLAUDE.md`, `pipelines/macro/CLAUDE.md`, `specs/38_funding-rates.md`. Add SOFR and the
> verified term series to `fred_series.py`. Verify the ECB Data Portal dataflows live; add an
> `ecb_client.py` in `pipelines/macro/` following `eurostat_client.py`'s pattern. Cassette
> tests. Register daily.

### Session B — wire in (~1 h)

> Replace Spec 14's constant with `fred.sofr` — its existing test must now pass on the real
> series. Add `carry_cost` and `implied_storage_premium` with the exact-figure test. One card on
> the curves page: front-spread contango decomposed into funding vs residual premium.

## Acceptance criteria

- [ ] No series ID guessed — every FRED and ECB ID verified live and recorded.
- [ ] Spec 14's SOFR-replacement test passes on real data.
- [ ] Day-count conventions explicit and tested.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
