# UK gas balance — the committed model files

This repo's own UK gas supply-demand model on DESNZ Energy Trends. A Bloomberg Intelligence
NBP calculator served as a layout example only.

    python -m pipelines.desnz_gas.pull
    python -m pipelines.derived.eu_gas_balance    # optional, for the EU mirror check
    python -m pipelines.derived.uk_gas_balance

## The question it answers

The UK has little gas storage, so the forward number is the **call on LNG**:

    LNG needed = demand + losses − production − biomethane − storage withdrawal
                 − net pipeline imports (Norway, continent, Ireland, Isle of Man)

On history this equals net LNG imports to within rounding (a test pins it). In a projection,
losses and the statistical difference are left out. The page shows their recent size.

## `routes.csv`

`type, country, route`. A `*` country catches the rest of its type. Imports count positive and
exports negative, so IUK and BBL, which flow both ways, are net. Totals in the flat sheet are
never routes.

## `assumptions.csv`

`line, year, yoy_pct, author, as_of, note`, the same format as `eu_gas/assumptions.csv`.
Lines are production, demand, biomethane, stock_change and the four pipeline routes. LNG is
not assumed: it is what the projection solves for. The committed file is a **persistence
baseline** (0%, `persistence baseline (default)`, 2026-10-26), a benchmark to replace with your own view.

## Checks (2026-10-26 run)

- Routes against published net imports: largest gap 2.2 mcm.
- Net-supply identity: 0.0 mcm.
- **EU mirror**: the UK's net exports to Belgium, the Netherlands and Ireland against the
  EU model's "United Kingdom" route. Correlation 0.995 over 126 months, with the EU recording
  a median of 34 mcm a month more since 2023: a measurement asymmetry between the two
  statistics, not a model error.
