# Spec 37 — ICE Commitments of Traders (Brent, Gasoil, TTF)

**Est. 3–4 h (two sessions) · Prereq: Spec 19 (CFTC COT, built — `pipelines/cftc/`).
New source: ICE weekly COT reports. Feeds Spec 19's COT percentiles and the crowding overlay.**

## Objective & alpha question

`pipelines/cftc/` covers the US-listed contracts: `cftc.<root>.mm_long / .mm_short /
.prod_merc_long / .prod_merc_short / .oi`. The two benchmarks most of the world's oil and
European gas actually price off — ICE Brent and ICE gasoil, plus TTF — report positioning to
ICE, not the CFTC. The crowding model is blind on exactly the contracts a European desk trades.

Question: *is managed money crowded in Brent or TTF at the same time it is crowded in WTI — and
when the two disagree, which one is right?*

## What Session A must verify live

- The ICE COT report location, file format and history depth for ICE Futures Europe (Brent,
  gasoil) and for TTF (which may be published under ICE Endex and/or under the EU MiFID II
  position-reporting format rather than the CFTC-style layout). **Record which format each
  contract uses** — they are not guaranteed to share categories.
- The trader categories each report carries, and how they map to the CFTC disaggregated
  categories already in the lake. Where a category has no clean equivalent, it gets its own ID
  and the mapping table says "no equivalent" — never forced into a CFTC bucket.
- Release day and the as-of (Tuesday-equivalent) date, for the publication-lag rule.
- Data terms: record ICE's terms in `pipelines/ice_cot/CLAUDE.md`.

## Data model

`ts_long`, `source="ice"`, mirroring CFTC naming so Spec 19 code can read both:
`icecot.<root>.mm_long`, `.mm_short`, `.prod_merc_long`, `.prod_merc_short`, `.oi`, plus any
ICE-only categories under their own names. Roots per conventions: `lco`, `g`, `tfm`.
`ts` = position as-of date; `revision_date` = ingestion time. A signal at *t* uses only rows
with `release_date <= t` — encode the release lag in the puller, tested.

## Sessions

### Session A — pipeline (~2 h)

> Read `CLAUDE.md`, `specs/00_TRADING_CONVENTIONS.md`, `specs/19_fundamentals-physical.md`,
> `pipelines/cftc/CLAUDE.md`, `specs/37_ice-cot.md`. Verify the ICE sources live. `/new-pipeline
> ice_cot`: client, history backfill, weekly puller, category mapping table as a CSV in the
> package. Cassette tests. Register weekly in `infra/run_scheduled.py`. Cross-check one week's
> Brent managed-money net against the published report and record both numbers.

### Session B — wire into Spec 19 (~1.5 h)

> Extend Spec 19's COT percentile functions to accept `icecot.*` roots without changing their
> signatures. Add a card on the positioning page: WTI vs Brent managed-money net percentile,
> side by side, and TTF on its own axis. Caption names both sources and states where categories
> are not like-for-like.

## Acceptance criteria

- [ ] Report formats verified per contract; category mapping table committed with "no
      equivalent" rows where true.
- [ ] Release-lag rule tested (a signal on the as-of Tuesday cannot see that week's report).
- [ ] Weekly pull idempotent; one week cross-checked against the published figure.
- [ ] Spec 19 functions read `icecot.*` unchanged in signature.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
