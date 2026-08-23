# Spec 09 — News Ingestion & Event Tagging Layer

**Week 14 · Est. 8–10 h · Prereq: Spec 00. Overlays onto every price/flow page.**

## Objective & alpha question
A timestamped, tagged event log (outages, sanctions, strikes, force majeure, OPEC decisions,
weather disasters) overlaid on charts turns "why did it move?" into a queryable record and builds
an event-study capability.

## Data sources — production-safe first
1. **GDELT 2.0** — free, no key, production-safe. DOC 2.0 API:
   `https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json&maxrecords=250&timespan=7d`.
   Primary source.
2. **The Guardian Open Platform** — free key (`settings.guardian_key`), full-text search, production-safe. Secondary.
3. **NewsAPI.org** — free Developer tier is **dev/testing only (cannot be used in production), 100 req/day, 24 h delay**. Use only for local experimentation; never in scheduled pulls. Flag any future publication use → paid tier decision.
4. **WorldNews API** — free ~50 pts/day; treat as optional supplement, same caution.

## Query dictionary (`pipelines/news/queries.py` — hand-curated, versioned)
Per (commodity × event-type): e.g. crude × outage: `("refinery" OR "pipeline") AND (outage OR fire OR explosion OR "force majeure")`;
gas × supply: `(LNG OR pipeline) AND (outage OR maintenance OR strike)`; sanctions: `(sanction OR "price cap" OR embargo) AND (oil OR crude OR tanker)`;
OPEC: `OPEC AND (quota OR cut OR meeting)`. Keep ≤10 focused queries.

## Data model
`events(event_id=hash(url), ts, headline, source, url, tags[], geo, commodity, severity)` in the lake.
Tagging: regex/keyword dictionaries per tag; geo via country-name dictionary; severity 1–3 by keyword tier
(3 = force majeure/explosion/embargo; 2 = outage/strike; 1 = general). Dedup: URL hash + fuzzy title
similarity (rapidfuzz ≥ 90) within 48 h.

## Visualisation spec
1. Page `09_events.py`: filterable event table (commodity/tag/severity/date) + events-per-week bar chart.
2. **Reusable overlay** `apps/dashboard/components/event_overlay.py`: `add_event_markers(fig, commodity, geo=None)`
   drawing severity-coloured vertical lines with hover headlines — then retrofitted onto pages 01, 02, 06, 07.

## Claude Code sessions

### Session A (weekday, 1 h) — GDELT client
> Read CLAUDE.md, specs/09_news-events.md. Scaffold `pipelines/news/`: GDELT DOC client with the
> query dictionary, mapping articles → events schema. Cassette test. Acceptance: a real crude-outage
> query returns tagged rows in the lake.

### Session B (weekend, 3 h) — tagging, dedup, Guardian
> Tagging engine (tags, geo, severity) with unit tests on crafted headlines; rapidfuzz dedup;
> Guardian client behind the same interface. Page 09 with table + weekly bars. Acceptance: running
> the pull twice creates zero duplicates; a "refinery fire Rotterdam" test headline tags
> (crude, outage, NL, severity 2+).

### Session C (weekday, 1 h) — overlays
> Build `event_overlay.py` and wire onto pages 01 (crude), 02 (gas), 07 (cracks). Daily entrypoint.

## Definition of Done
- GDELT + Guardian ingesting on ≤10 curated queries; tagged, deduped, severity-scored.
- Event table page + overlay live on ≥3 chart pages. NewsAPI absent from scheduled pulls. Tests green.

## Stretch
- Claude-API tagging pass for untagged headlines (batch, cached, budget-capped).
- Event study: median price move ±5 days around severity-3 events per commodity.
