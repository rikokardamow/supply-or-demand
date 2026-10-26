# Spec 39 — Carbon (EUA) and the Fuel-Switching Price

**Est. 4–5 h (two sessions) · Prereq: Spec 04 (ENTSO-E power, built), Spec 34 (if EUA comes via
IBKR). New source: EUA prices. Unblocks the dark/clean spread analytics Spec 14 dropped for
want of carbon and coal.**

## Status (2026-10-26)

Session A, partly built: `pipelines/carbon` pulls EEX primary auctions (2020 onwards, `eex.eua.auction.*`
including `cover_ratio`) and the Union Registry installation file. A separate EU ETS allowance
balance (`pipelines/derived/eu_carbon.py`, page `27_eu_carbon.py`) is built on them. Still open:
the IBKR EUA futures route, EEX terms of use, the API2 coal source, and Session B (switching price).

## Objective & alpha question

Spec 04 noted "add EUA price when available"; Spec 14 dropped clean spark and dark spreads
because the lake had neither carbon nor coal. Power and gas are both in. Carbon is the missing
third leg of every European generation-margin trade.

Question: *at what EUA price does gas displace coal in German power at today's TTF — and how
far is the market from that switching point?* The distance to the switching price is a
positioning signal across TTF, EUA and German baseload at once.

## Sources — Session A verifies live, in this order of preference

1. **ICE EUA futures via IBKR** (Spec 34 symbol discovery, add `eua` to `contract_specs.csv`).
   Exchange settlements, full curve. Preferred if entitled.
2. **EEX primary auction results** — free, daily, but an auction clearing price, not a
   continuous market price. Usable as a cross-check and history; labelled as auction.
3. **Coal (API2 Rotterdam)** — no known free source. If none is verified, the dark spread is
   computed with a **manual monthly coal CSV** (`data/manual/coal/api2_*.csv`, `source="manual"`)
   and the card says so. Never substitute a US coal series for API2.

Record terms of use for each in `pipelines/carbon/NOTES.md`. EEX data terms may restrict
redistribution — if so, the series stays in the lake and off the public site, recorded.

## Data model

`ts_long`: `fut.eua.<contract>.settle` (via the futures pipeline if IBKR), `eex.eua.auction.price`
and `.cover_ratio`, `manual.coal.api2.m01`. Derived: `derived.power.de.clean_spark`,
`derived.power.de.clean_dark`, `derived.power.de.switch_price_eua`.

## Analytics — `core/power_spreads.py` (pure)

```python
def clean_spark(power: pd.Series, gas: pd.Series, eua: pd.Series,
                heat_rate: float = 1 / 0.50, ef_gas: float = 0.202) -> pd.Series
def clean_dark(power: pd.Series, coal_usd_t: pd.Series, eua: pd.Series, fx: pd.Series,
               eff: float = 0.38, ef_coal: float = 0.341) -> pd.Series
def switching_price(gas: pd.Series, coal: pd.Series, fx: pd.Series, **params) -> pd.Series
```

Efficiencies and emission factors are parameters with sources cited in the docstring, not
magic numbers. Units handled explicitly (€/MWh, $/t, tCO2/MWh-thermal). Test: at the switching
price returned, clean spark equals clean dark to the cent.

## Sessions

### Session A — carbon (and coal) sources (~2 h)

> Read `NOTES.md`, `specs/04_entsoe-eu-power.md`, `specs/39_carbon-eua.md`. Verify the EUA
> sources live in the order above; record entitlement and terms. Build whichever is available:
> extend the futures pipeline for `eua` via IBKR, and/or `/new-pipeline carbon` for EEX auctions.
> Manual coal CSV reader if no coal source verifies. Cassette/fixture tests.

### Session B — spreads and page (~2.5 h)

> Build `core/power_spreads.py` with the switching-price identity test. Derived series step in
> `pipelines/derived/`. Card on the EU power page: German clean spark vs clean dark, and EUA
> against its switching price, with the gap annotated. Caption names every input's source and
> marks coal as manual where it is.

## Acceptance criteria

- [ ] EUA source verified and labelled (exchange settle vs auction); terms recorded.
- [ ] No US coal series ever substituted for API2 (tested: missing API2 → NO-DATA, not a proxy).
- [ ] Switching-price identity test passes.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
