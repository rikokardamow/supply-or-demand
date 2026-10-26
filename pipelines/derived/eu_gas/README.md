# EU gas balance — the committed model files

This repo's own EU-27 gas supply-demand model. A Bloomberg Intelligence TTF calculator served
as a layout example only; its method, figures and assumptions are not used. Structure and route
choices are documented in `docs/superpowers/specs/2026-10-26-eu-uk-gas-model-mapping.md`.

    python -m pipelines.eurostat_gas.pull
    python -m pipelines.derived.eu_gas_balance

## `routes.csv` — which partner is which route

One rule per partner and product (`pipeline` or `lng`), optionally dated with `valid_from` /
`valid_to` (month starts, inclusive). A `*` row per product catches every other partner. EU
members are never mapped: intra-EU trade is excluded before mapping. The derived step raises on
an unmapped partner, an overlapping rule or an unknown route, because silently dropping a
partner would remove gas from the balance.

The dated rules record real events:
- Ukraine transit of Russian gas ended 1 January 2025. Before that, `ua` is Russian pipeline
  gas; after, it is net EU exports to Ukraine.
- The Maghreb–Europe pipeline closed on 31 October 2021. Before that, `ma` is Algerian gas;
  after, Spain sends gas the other way.

The south-east corridor (Türkiye, Serbia, Albania, North Macedonia, Azerbaijan, Georgia) mixes
Russian TurkStream gas and Azeri TAP gas at one border. Eurostat cannot split them, so neither
does this model.

## `assumptions.csv` — the projection

`line, year, yoy_pct, author, as_of, note`. `line` is a route or `production` /
`consumption`. A projected month equals the same month a year earlier × (1 + yoy_pct/100). A
line or year with no row is not projected; it is not assumed flat. The derived step refuses a
row with no author or date.

The committed file is a **persistence baseline**: 0% for everything, by `claude-code`,
2026-10-26. It is a benchmark, not a view. Replace it with your own rates.

## Checks the model runs on itself (shown on page 25)

- Eurostat stock change against GIE's month-end storage change, in TWh: correlation 0.998, a
  median gap of 3.4 TWh over 88 months (2026-10-26 run).
- Intra-EU asymmetry: Eurostat imports − exports against the sum of routes. The median is
  0.4 bcm a month since 2021, the largest 2.6.
- Unexplained: production + routes − consumption against reported stock change. Same scale.
