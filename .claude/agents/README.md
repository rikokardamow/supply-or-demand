# Project agents

Six domain agents for this repo, aligned to the clusters in the reading corpus at
`~/Desktop/skill-pdfs` (~90 books, manuals and journal articles, plus the owner's own
Bloomberg Intelligence models).

| Agent | Owns |
|---|---|
| `oil-balance-modeller` | supply/demand balances, regional demand regressions, spare capacity, scenarios |
| `refining-biofuels-modeller` | cracks, refinery configuration, RIN/RVO, SREs, feedstocks, ethanol |
| `curve-derivatives-analyst` | curve structure, spreads, carry, roll, options, systematic signals |
| `benchmarks-physical-analyst` | PRAs and assessed prices, quality and differentials, OSPs, freight and LNG arb, sanctions and AIS |
| `risk-forecast-analyst` | VaR and tail risk, volatility models, stress, and evaluating **any** forecast |
| `energy-exhibit-builder` | every chart, map and exhibit, in house style |

## Skills say how to read a result; agents do the work

`SKILL.md` in the corpus folder is the already-distilled domain reference — 21 sections,
69 KB, built from the same ~90 documents. It is a passive reference. These agents are
dispatchable workers that **read it first** and then change the repo.

Do not duplicate SKILL.md into an agent. If a rule belongs to the domain rather than to a
task, it belongs in SKILL.md; the agent points at the section.

**The agents have not absorbed the corpus.** No agent definition can hold 721 MB. What each
one carries is the distilled non-negotiables for its area, an index of which document
answers which question, and the repo conventions it must obey. The reading happens on
demand, per task. Treat a claim an agent makes about a book it has not opened in that
session as unverified.

## Orchestration

Typical order for a new model, each stage handing the next a concrete artefact:

```
domain modeller          -> what to measure, which series, which assumptions
  benchmarks-physical    -> are these series actually comparable?   (gate)
  risk-forecast          -> what does it beat, out of sample?        (gate)
energy-exhibit-builder   -> how it renders
```

The two gates are the point. Most errors here are domain errors, not code errors, and both
gates exist to catch a specific recurring one: joining series that were never comparable,
and shipping a model that nobody scored.

Dispatch in parallel only where the work is genuinely independent — two unrelated pipelines,
say. A modeller and its gate are sequential by construction.

## Standing rules every agent inherits

Read the repo root `CLAUDE.md` first; its golden rules win over anything here. Beyond those:

- Confirm live; never guess a series id, a route or a signature. `read_ts_long()["series_id"].unique()` is one line.
- Degenerate inputs fail loudly. Never substitute a plausible stand-in.
- No data is not zero, and a missing counterpart is `None`, never `0.0`.
- Exclude 2020 from every seasonal construct.
- Ask before adding a dependency or changing a schema.
- British English throughout.
- End green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

## Licensed material

The owner's workbooks in the corpus folder are Bloomberg Intelligence products carrying a
`BI Disclaimer` sheet. Port the method; never commit a workbook; never republish BI figures
to a remote surface. `data/manual/**` is git-ignored for this reason, and nothing in this
project is currently hosted.
