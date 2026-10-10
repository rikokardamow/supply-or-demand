# Hormuz scenario assumptions

Inputs to `pipelines/derived/hormuz.py`. Split across two places on purpose.

## Committed here — the scenario levers

These are the user's own choices and belong in a diff, following the
`pipelines/opec_momr/quotas.csv` precedent for a hand-maintained reference file.

`recovery_ceilings.csv` — `producer,recovery_ceiling`

How much of its lost rate a producer ever regains, 0–1. A **cap, not a speed**: at a fully
reopened strait a producer with 0.8 is still 20% of its loss short, permanently. The source
workbook calls this a "Ramp (Recovery) Factor", which reads like a rate; the formula is a
ceiling, and `core.hormuz.ProducerDisruption.recovery_ceiling` is named for what it does.

`flow_share.csv` — `quarter,open_share`

Assumed share of normal Hormuz flows per quarter, 0–1. **A blank is not a zero.** Blank
means not known and writes no rows; zero asserts a total closure. The source workbook writes
its pre-disruption quarter as `-` for this reason.

## Not committed — the baselines

`data/manual/hormuz/baselines.csv` — `producer,quarter,undisrupted_mbd,disrupted_mbd`

Each producer's bounding rates per quarter. Kept in the git-ignored drop because they derive
from a licensed Bloomberg Intelligence workbook. `data/manual/**` is ignored wholesale; do
not move this file into the repo.

Without it the pipeline raises `FileNotFoundError` naming the path, rather than writing a
partial scenario.

## A real error in the source, found by porting it

Checked 2026-10-10 against the workbook's own `Scenario` columns, which are **not** inputs
to this pipeline — they are the figures it publishes. 35 cells compared across 7 quarters
and 5 producers:

- **30 of 35 match exactly**, difference 0.00e+00.
- **All five mismatches fall in 1Q 2027**, and are the workbook's error, not this port's.

The workbook's scenario formulas reference flow-share cells `$E$4, $F$4, $G$4, $G$4, $I$4,
$J$4, $K$4` across the seven quarters. The fourth should be `$H$4`. `H4` is skipped, so
1Q 2027 is computed with 4Q 2026's 0.8 while its own stated assumption is **0.9**.

Every one of the five producers is understated for that quarter as a result, and the error
feeds `Surplus / (Deficit)` directly.

The per-producer magnitudes are deliberately not printed here, and neither is the Gulf
total. **A scenario output is a licensed figure in disguise.** `recovery_ceilings.csv` and
`flow_share.csv` are tracked, so anyone holding this repo has every term of
`scenario = disrupted + (undisrupted - disrupted) * open_share * ceiling` except the two
baselines. Two scenario figures for the same producer at different shares -- exactly what a
published-against-correct pair is -- leave two equations in those two unknowns and invert to
the licensed rates exactly. Reproduce the comparison yourself from
`data/manual/hormuz/baselines.csv`; the finding is the skipped cell reference, which needs
no numbers to state.

This pipeline uses each quarter's own share. It therefore disagrees with the workbook in
1Q 2027 deliberately. Recorded here rather than reconciled, per
`specs/00_TRADING_CONVENTIONS.md`: a miss is a visible diagnostic, never a silent pass.

## Running it

```
.venv/Scripts/python.exe -m pipelines.derived.hormuz
```

Not scheduled. A scenario changes when its assumptions change, not on a clock — running it
nightly would rewrite identical rows and imply the numbers had been refreshed from a source.
Run it by hand after editing an assumption.

## What it writes

`derived.hormuz.scenario.<producer>.supply`, `derived.hormuz.scenario.gulf_total.supply`
(mb/d, quarterly) and `derived.hormuz.scenario.open_share` (the assumption itself, so a
chart can state what it is conditional on). Every id carries `scenario` so no reader can
mistake these for observations. The Gulf total is NaN wherever any producer is unknown —
summing around a gap would publish a number that looks regional and is not.

## The baselines, checked against real production (2026-10-10)

The `disrupted_mbd` column is not a guess. Checked against OPEC's own per-country
secondary-source production, restored into the lake from the June 2026 MOMR PDF
(`python -m pipelines.opec_momr.pull_doc_crude <pdf>` — 176 rows, 22 countries; that
pipeline has no automated download, see `pipelines/opec_momr/CLAUDE.md`).

The comparison is recorded here in prose rather than as a table: the per-producer
undisrupted and disrupted rates are licensed BI figures and live only in the git-ignored
drop. OPEC's own production numbers are public, but a table pairing them column-by-column
with BI's assumptions reproduces the licensed half, so it is not reproduced.

Two readings, both worth keeping:

**The disrupted floors are real, not invented.** Observed May 2026 production sits close to
the workbook's disrupted assumption for every one of the five producers, and for the UAE it
matches to within a hundredth of a million barrels per day. The undisrupted column is the
counterfactual; comparing actuals against *it* — as a first pass of this check wrongly did —
produces nonsense gaps of several hundred per cent.

**But every floor is optimistic against the latest observed month.** All five actuals come in
at or below their assumed disrupted rate, Iran by the widest margin and Saudi Arabia next. A
scenario anchored on these floors therefore starts from a slightly better position than the
market was actually in as of May 2026. Recorded, not adjusted: the baselines are the
workbook's, and changing them silently would make this port something other than a port.

The three-month trajectory also shows the disruption still deepening through the window, so
no single month should be treated as the floor. Reproduce the figures yourself from
`momr.doc_crude_secondary.*` in the lake against the git-ignored drop.
