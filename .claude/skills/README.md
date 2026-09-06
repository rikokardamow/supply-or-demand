# Project skills

Skills Claude Code loads automatically when working in this repo. Each is a distilled reference,
not a document dump — the source PDFs stay outside the repo in `~/Desktop/skill-pdfs`.

| Skill | Covers |
|---|---|
| `energy-analyst` | Single consolidated domain reference for the petroleum, gas and power complex |

## What `energy-analyst` covers

Twenty-one sections, jumped into by topic rather than read front to back:

| § | Topic | Related spec |
|---|---|---|
| 1–3 | Units and conversions; the physical chain (title, Incoterms, posted prices); crude quality | cross-cutting |
| 4 | Benchmarks and PRAs — MOC vs VWA, Dated Brent composition, the benchmark ecosystem | cross-cutting |
| 5–6 | Curve structure, storage economics and optionality; spread taxonomy | cross-cutting |
| 7 | Refining — configuration ladder, crack interpretation, hedge-ratio caveats | 07 |
| 8 | OPEC — MOMR table conventions, revision vintages, spare capacity | 06 |
| 9–11 | Gas price formation; LNG chain, cost stack, arbitrage and freight; US gas structure and storage | 02, 03, 05, 11 |
| 12–14 | Power and spark/dark spreads; basis, volumetric and credit risk; volatility structure | cross-cutting |
| 15–16 | Price-control regimes, shock decomposition, macro transmission, tails; demand elasticities | cross-cutting |
| 17 | Macro indicator releases — revision cascades, vintages, lead/lag | 10 |
| 18 | Forecast evaluation — out-of-sample discipline, benchmarks, metric traps | Chronos work |
| 19–20 | Spot–futures behaviour; sanctions, dark fleet and AIS interpretation | 11 |
| 21 | Common mistakes — a scan-first table of 27 failure modes and their fixes |

## How this was built

Source corpus: 89 PDFs (85 unique documents) in `~/Desktop/skill-pdfs` — trading manuals, energy
economics textbooks, risk and derivatives texts, and ~30 journal articles. **The full corpus has
been mined; no group remains outstanding.** Triaged as follows:

- **Became the skill** — stable, procedural or definitional knowledge referenced repeatedly:
  trading manuals, PRA methodology, indicator handbooks, and the empirical findings from the
  academic papers.
- **Rejected as data, not knowledge** — dated market reports (OPEC MOMR, Vitol demand outlook, bank
  commodity notes, trade recommendations). These go stale; ingest them, don't encode them. The MOMR
  was read only for its *table structure*, which is stable.
- **Rejected as out of scope** — narrative histories, trader memoirs, reflexivity and
  qualitative-research material, equity volatility-arbitrage papers, AML/sanctions case files, and
  personal documents. Where a nominally out-of-scope source contained a durable mechanism, it was
  pulled in anyway (the dark-fleet/AIS taxonomy, the posted-price origin of OPEC).

Every factual claim is traceable to a source named in the skill's `## Sources and provenance`
section. Where sources disagreed, the disagreement is documented rather than resolved silently —
see "never say buy the crack" in §7, and the supply-elasticity tension in §15.

## History

This began as seven topic skills (`oil-market-conventions`, `refinery-crack-spreads`,
`price-benchmarks-and-pras`, `opec-supply-analysis`, `lng-arbitrage-and-shipping`,
`macro-indicator-releases`, `commodity-forecast-evaluation`), written before the deep corpus pass
had finished. They were consolidated into `energy-analyst`, which is a strict superset: it carries
all of their content and adds gas price formation, the LNG cost stack, power and spark spreads,
basis decomposition and volumetric risk, volatility structure, price-control regimes, storage
optionality, and the AIS interpretation rules behind Spec 11.

The seven were removed to avoid overlapping trigger conditions. Copies are kept outside the repo at
`~/Documents/claude-recovery-35044e9a/skills/` if any of that phrasing is ever wanted back.

## Known gaps

- **EU gas storage and flows are under-served.** Specs 02/03/05 need AGSI+/ALSI+ and ENTSOG
  methodology documentation; the corpus's only gas-fundamentals candidate was 2013-vintage and
  US shale-focused.
- **No cushion-gas / working-gas ratios or deliverability curves** — not quantified anywhere in the
  corpus. Source from AGSI+/ALSI+ or operator documentation.
- **No EIA WPSR parsing conventions** — no methodology document in the corpus; the WPSR PDFs are
  data releases, not specifications.

## Adding more

Skills are directories containing `SKILL.md` with `name` and `description` frontmatter. The
description states *when* to use the skill and nothing about what it does — a description that
summarises the workflow gets followed instead of the skill body. If a future skill is narrow and
frequently loaded, keep it under ~500 words and push heavy reference into a sibling file loaded on
demand; `energy-analyst` is deliberately the exception, a single long reference kept whole.
