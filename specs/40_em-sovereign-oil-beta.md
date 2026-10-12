# Spec 40 — EM Sovereign Spreads vs Oil (oil-beta relative value)

**Est. 5–6 h (three sessions) · Prereq: Spec 10 (macro/FX), Spec 18 (futures), Spec 34 (IBKR) for
Sessions B–C. New sources: TCMB EVDS (Turkey), EM sovereign proxies via IBKR.**

## Objective & alpha question

Oil importers and oil exporters carry opposite sovereign sensitivity to the barrel: a Brent
rally widens an importer's current-account gap and tightens an exporter's fiscal position. The
lake has oil in depth and EM sovereign risk not at all.

Question: *does the importer-minus-exporter sovereign spread move with Brent at a stable beta —
and when it diverges from that beta, does it converge?* A cross-asset relative-value book
hedged with oil futures.

## The honest constraint, stated first

**Sovereign CDS has no free source.** Work Bloomberg is not available for a personal project
under compliance approval. This spec therefore builds the trade on **bond-market proxies**, and
every card says so. If a CDS source is ever verified, it is added beside the proxy, never in
place of it.

## Sources — Session A verifies live

| Leg | Source | Notes |
|---|---|---|
| Turkey local yields, policy rate, FX | TCMB EVDS API (free key) | verify current API version, auth header and series codes live; add `EVDS_API_KEY` to `.env.example` |
| Turkey USD sovereign | IBKR bond or country/sovereign ETF prices (Spec 34) | verify which instruments are entitled |
| EM USD sovereign aggregate | IBKR EM sovereign bond ETF | proxy for the EMBI-style spread, labelled |
| Exporter leg (Gulf sovereigns) | IBKR — verify what is tradable/priced | if nothing verifies, the exporter leg is dropped and the trade becomes importer vs UST, recorded |
| US Treasury benchmark | FRED `DGS5`, `DGS10` (existing client) | for spread construction |

Record every instrument chosen, why, and what failed in `pipelines/em_sovereign/CLAUDE.md`.

## Data model

`ts_long`: `evds.<series_code_lower>` for EVDS, `ibkr.<instrument>.close` for IBKR prices,
`derived.em.<country>.spread_proxy_bp`, `derived.em.oil_beta.<pair>.beta_252d`,
`derived.em.oil_beta.<pair>.residual_z`.

## Analytics — `core/em_rv.py` (pure)

```python
def spread_proxy(yield_or_price: pd.Series, ust: pd.Series, kind: str) -> pd.Series   # bp
def rolling_beta(y: pd.Series, x: pd.Series, window: int = 252) -> pd.DataFrame        # beta, r2, se
def residual_z(y, x, beta: pd.Series, window: int = 252) -> pd.Series
def hedge_ratio_contracts(dv01_or_notional: float, beta: float, fut_mult: float,
                          fut_price: float) -> float
```

Betas use only data available at *t* (rolling, never full-sample — the Spec 20 look-ahead bug
is the precedent). A structural-break test date is shown on every beta card, per the model-page
conventions.

## Sessions

### Session A — EVDS pipeline (~2 h)

> Read `CLAUDE.md`, `specs/10_macro-fx.md`, `specs/40_em-sovereign-oil-beta.md`. Verify EVDS
> live; record API version, auth and the series codes for Turkish 2Y/10Y yields, policy rate
> and USD/TRY. `/new-pipeline evds`. Cassette tests. Register daily.

### Session B — IBKR proxies (~2 h)

> With Spec 34 live, verify which EM sovereign instruments are priced on the paper account.
> Pull daily closes for the chosen set. Record every instrument tried and the result.

### Session C — beta, residual, page (~2 h)

> Build `core/em_rv.py` with tests (a synthetic series built as 2×Brent + noise returns beta ≈ 2
> within tolerance). Card: importer-minus-exporter spread proxy vs Brent, rolling beta with its
> break date, residual z-score, and the futures hedge ratio. Caption: "bond-market proxy, not
> CDS".

## Acceptance criteria

- [ ] CDS absence stated on every card; no proxy presented as CDS.
- [ ] EVDS and IBKR instruments verified live, including failures.
- [ ] Rolling beta has no look-ahead (shift test, as in Spec 20).
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
