# Reading guide

The project's working documents were written while building it, so they use spec numbers and short names. This page says what each one is for. The README is the summary; this is the map.

## How the pieces fit

```
public sources  ->  pipelines/<source>/   ->  data/lake/ (Parquet, read with DuckDB)
                                          ->  pipelines/derived/publish_series  ->  Postgres serving layer
                                                                                 ->  web/ (data site), site/ (landing page), apps/dashboard/ (Streamlit)
```

Pipelines write the lake and never draw. The sites read the serving layer and never call a source API. The lake is the source of truth; the serving copy is derived from it and carries a provenance log.

## The documents

| File | What it is |
|---|---|
| `README.md` | What the project is, the charts, how to run it |
| `DEVELOPMENT.md` | The conventions: golden rules, stack, schemas, commands, the code-review procedure, the chart house style, the credential rules |
| `CHANGELOG.md` | The build log, spec by spec: what was verified live against each API and what broke |
| `specs/00_INDEX.md` | The index of specifications |
| `specs/NN_*.md` | One specification per feature, numbered in build order (see below) |
| `specs/00_TRADING_CONVENTIONS.md`, `specs/TRADING_LAYER_RUNBOOK.md` | Units, benchmarks and procedures for the analytics layer |
| `pipelines/<source>/NOTES.md` | What was checked live against that source's API, and its terms |
| `infra/README.md`, `infra/DISASTER_RECOVERY.md` | Scheduling and recovery |
| `artifacts.md` | How the published exhibit pages and Office exports are rebuilt |
| `weather-module-spec.md` | A draft specification for the weather module |
| `NOTICE` | Credits for adapted code |

## The specification numbers

| Specs | What they cover |
|---|---|
| 00 | Project setup and conventions |
| 01 to 12 | One data source each: EIA by region, EU gas storage, EU gas flows, EU power, US gas and power, OPEC, refining margins, weather, news, macro and FX, vessels, flights |
| 13 | Orchestration and tests |
| 14 | The analytics layer |
| 15 to 17 | Sanctions, a news supplement, a sentiment overlay |
| 18 to 27 | The trading analytics layer: curve structure, physical fundamentals, refining econometrics, systematic signals, risk, macro, volatility, freight, gas analytics, the journal |
| 28 | A geopolitical-risk module adapted from an external design (28.00 to 28.11 are its chapters) |
| 29 to 31 | Social sentiment, EIA price coverage and extensions |
| 32, 33 | The Postgres serving layer and the Next.js front end |

## The shapes

Every value in the lake is written in one of four shapes, defined in `core/schemas.py` and validated on write:

- `ts_long`: one number for one series at one time, with its unit, geography, frequency and revision date.
- `flows`: a quantity moving from one place to another, with a mode.
- `events`: a tagged news or policy event.
- `vessel_positions`: an AIS position report.

## The two kinds of chart

- `docs/img/*.png`, in the README, are drawn with matplotlib by `apps/exhibits/readme_charts.py` from the lake.
- The dashboards draw with Plotly in the browser, using the theme in `core/theme.py`. `apps/artifacts/` publishes standalone exhibit pages from the same lake.

## Data that is not in git

`data/` holds the lake and the raw downloads. It is rebuilt by the pipelines; most need a free API key, listed in `.env.example`.
