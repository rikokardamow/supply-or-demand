# Spec 33 — Front-end (Next.js on Vercel) — Overview

**Status:** v2, supersedes the FastAPI/Vite version · **Depends on:** Spec 32 (serving layer), Spec 28 (GRP) · **Drops:** FastAPI, Grafana, Railway.

> Renumbered from the original draft's "Spec 29" — that number is already taken by
> `29_social-sentiment-self-hosted.md` (done, live-verified). This is Spec 33; the
> serving-layer companion is Spec 32.

> Set: 33.00 (this), 33.01 Hormuz, 33.02 Balances. Gas (33.03) and Curves (33.04) stubbed at the end.

## 1. Objective

One desk-grade web UI at `data.kardamow.com` in the house exhibit style: the public read-only showcase now, the paid desk tier later without a rewrite, every panel exportable straight into an article. The UI reads Supabase; it never computes.

Non-goals for v1: auth, user settings, mobile beyond readable, editing anything.

## 2. Architecture

```
pipelines/ (Python, DuckDB)  ──GitHub Actions cron──▶  Supabase Postgres (serving tables, Spec 32)
                                                              │
                                              Next.js on Vercel ◀── reads via supabase-js
                                              ├─ server components + ISR for the page shell and tables
                                              └─ client components + TanStack Query for charts, map, live refresh
```

- No API service of our own. Supabase's PostgREST is the API; access is scoped by RLS (Spec 32 §4).
- Two read paths, chosen per panel: **ISR** (server-rendered at build, revalidated on a schedule or on pipeline publish) for anything that changes once a day or week; **client query** for anything that refreshes intra-day (AIS, GRP) or reacts to filters.
- Heavy compute (backtests, GRIB rendering) is not in the UI or Supabase; it stays in Python. If it ever needs to run on demand, Modal or Railway is held in reserve behind a Supabase Edge Function. Not v1.

## 3. Stack (pinned — ask before changing)

| Layer | Choice | Why |
|---|---|---|
| Framework | Next.js 15, App Router, TypeScript strict | Vercel-native; RSC + ISR fits daily/weekly data |
| Hosting | Vercel, Hobby → Pro when the paid tier lands | Zero-ops, preview deploys per PR |
| Data | Supabase Postgres (Frankfurt), supabase-js v2 | Serving tables from Spec 32; RLS for the paid tier later |
| Styling | Tailwind + shadcn/ui | Dense, quiet, readable |
| Charts | Plotly.js via react-plotly.js (client component, dynamic import, `ssr: false`) | Same library as `core/theme.py` |
| Curves | TradingView lightweight-charts (client) | Desk-native strips and ladders |
| Maps | MapLibre GL via react-map-gl (client) | WebGL for AIS density |
| Client data | TanStack Query | Caching, refetch intervals keyed to the release calendar |
| State | Zustand (filters only) | |
| Types | `supabase gen types typescript` → `src/types/database.ts` | Schema and UI cannot drift |
| Tests | Vitest + Playwright | Playwright is also how Claude Code sees the screen |

Do not add: Recharts, Redux, a second component library, an ORM, tRPC, a Next API route that proxies Supabase (RLS makes it unnecessary and it doubles latency).

## 4. Design tokens

New for this repo (there is no v1 `web/` yet — NOTES.md's chart house style lives in
`core/theme.py`/`core/design.py` for the Python/Streamlit side only). Port those same
tokens rather than inventing new ones: `web/src/theme/tokens.css` and
`plotly-template.json` should mirror `core/design.py`'s navy `#0f2a4a` primary, light
blue `#5b9bd5` secondary, red `#c0392b` accents, orange `#e67e22` median, grey seasonal
band, white paper, light grid `#e6e6e6`. Confirm the exact current token values from
`core/design.py` at build time rather than hand-copying this list — it is a paraphrase,
not the source of truth. Font: the dashboard now uses Inter/Lora (see root `NOTES.md`'s
"Dashboard layout" section, updated after this draft was written) — use the same pairing
here for visual consistency across the Streamlit and Next.js surfaces, not the IBM Plex
Sans originally drafted, unless a later session deliberately picks a distinct web identity.
Chart rules (relationship-stating titles, last-point annotations, source line, no 2020 in
bands) carry over verbatim from `core/theme.py`.

## 5. Layout system

**Decision:** match the live Streamlit app's post-restyle chrome (`apps/dashboard/app.py`,
root `NOTES.md` § "Dashboard layout — institutional look"), not the left-rail layout
this section originally described — that rail predates the 2026-09-08 restyle and no
longer reflects the product. One consistent visual identity across both surfaces:

- **Masthead**: a centred "Kardamow" wordmark (`HEADING_STACK` i.e. Lora, `TEXT` colour,
  ~3.25rem, weight 600) over a hairline rule (`RULE` colour), exactly mirroring
  `apps/dashboard/app.py`'s `<h1>` + `<hr>`. This is the page's only `<h1>`.
- **Navigation**: grouped **top** navigation beneath the masthead — no left icon rail,
  no sidebar. Mirrors Streamlit's `st.navigation(..., position="top")` via `nav.py`.
- Below that: one row of filter selects and the as-of stamp, then the main 12-column
  grid, 12px gutter, panels on white with a 1px rule (`RULE`). Panel header = title +
  source line (`components.section.section()`'s pattern: `<h3>` + hairline), body =
  chart or table. Nothing decorative.
- Left-aligned text; numbers right-aligned in tables.
- Headings use `HEADING_STACK` (Lora); all in-chart strings (axis ticks, legends, data
  labels) and body copy stay on `BODY_STACK` (Inter) — numbers never render in the serif,
  matching the Streamlit app's rule verbatim.

No `mockups/*.html` exist yet in this repo. Session A of §8 should produce a static
mockup of this masthead+top-nav layout (or a Playwright screenshot of the equivalent
Streamlit chrome, annotated) before wiring real components, so there is something
concrete to diff against.

## 6. Data access (replaces the FastAPI contracts)

Every panel binds to one Spec 32 table or view. Names are fixed here so the screen specs can refer to them.

| Panel need | Supabase object | Read path |
|---|---|---|
| Any scalar series | `serving.series_long` (filter `series_id`, `ts >= from`) | ISR for weekly/daily, client for intra-day |
| Seasonal chart | `serving.seasonal_v` (one row per `series_id`, `doy`: `band_min`, `band_max`, `median`, `current`, `prior`) | ISR |
| WPSR table | `serving.wpsr_latest_v` | ISR, revalidate on publish |
| Flows | `serving.flows` (filter `from_node`, `to_node`, `period`) | ISR |
| Vessel positions | `serving.vessel_latest_v` (last position per MMSI, bbox filter via `ST_MakeEnvelope`) | Client, 5 min |
| GRP | `serving.grp_scores` (latest + history), `serving.grp_components_v` | Client, 15 min |
| Curve | `serving.curve_settles` (filter `root`, `trade_date`), `serving.spreads_v` | ISR daily |
| Meta / as-of | `serving.publish_log` (one row per table per publish: `table_name`, `as_of`, `source_note`, `published_at`) | Both |

Conventions:
- Queries live in `src/data/queries/*.ts`, one function per table, typed from `database.ts`. Components never call `supabase.from()` directly.
- `as_of` for a panel always comes from `publish_log`, never inferred from max(ts). The `AsOfBadge` greys a panel when `published_at` is older than the table's expected cadence (Spec 32 §5) — mirroring, on the web side, the same freshness logic `core/freshness.py` already implements for the Streamlit app (see `EXPECTED_CADENCE_DAYS`); keep the two cadence tables in sync by hand until/unless one is generated from the other.
- Revalidation: pipelines call `POST /api/revalidate?tag=<table>` on Vercel after a successful publish (secret in `REVALIDATE_SECRET`). Pages use `unstable_cache`/`revalidateTag` keyed by table name. Fallback schedule: `revalidate = 3600`.
- Client queries use the anon key with RLS granting `SELECT` on `serving.*` to `anon`. No service-role key ever reaches the browser or the repo.

## 7. Repo layout

```
web/
  app/
    layout.tsx                 chrome: TopBar, Rail, fonts, tokens
    (screens)/
      hormuz/page.tsx          RSC shell; client islands for map, GRP, charts
      balances/page.tsx        RSC: table + seasonal data fetched server-side, charts as client islands
      gas/page.tsx  curves/page.tsx
    api/revalidate/route.ts    tag revalidation endpoint for the pipelines
  src/
    theme/                     tokens.css, plotly-template.json, applyTemplate.ts
    data/
      supabase/{server.ts,client.ts}   createClient variants
      queries/                 series.ts, seasonal.ts, wpsr.ts, flows.ts, vessels.ts, grp.ts, curve.ts, publishLog.ts
    types/database.ts          generated
    store/filters.ts
    components/
      chrome/   TopBar, Rail, Panel, AsOfBadge, SourceLine, ExportButton
      charts/   SeasonalChart, DualAxisChart, StackedFlows, HeatTable, CurveLadder   (all "use client")
      map/      StraitMap, VesselLayer, ChokepointLayer                                ("use client")
    lib/format.ts              numbers, units, dates — British English
  tests/                       vitest unit, playwright e2e + screenshot baselines
  .env.example                 NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, REVALIDATE_SECRET
```

`web/` is a new top-level directory alongside the existing `apps/dashboard/` (Streamlit)
— the two front ends coexist; this spec does not remove or replace the Streamlit app.

## 8. Claude Code workflow

Prerequisites: Spec 32 tables exist and at least `series_long`, `seasonal_v`, `wpsr_latest_v`, `publish_log` are populated by one real pipeline run.

1. Tooling: Node 22 + pnpm; Vercel CLI (`vercel link`); Supabase CLI (`supabase login`, `supabase gen types`); `.mcp.json` with Playwright, shadcn, Context7, and the Supabase MCP for schema inspection. Skills: `interface-design` (tokens written in first), `frontend-design`.
2. Session A (weekend): `create-next-app` in `web/`, tokens + Plotly template, chrome components, `SeasonalChart` fed from `seasonal_v` via a server component. Playwright screenshot vs the mockup produced this session (§5).
3. Session B (weekend): Balances screen complete (33.02) including `HeatTable` from `wpsr_latest_v`, `AsOfBadge` from `publish_log`, revalidate route wired and tested with `curl`.
4. Session C (weekend): Hormuz screen (33.01): `StraitMap` on `vessel_latest_v`, GRP panel on `grp_scores`, three charts.
5. Weekdays: `format.ts`, empty/error states, export button, screenshot baselines, Vercel preview → production on `data.kardamow.com`.

Session rules: read 33.00 + the screen spec + 32.00 before coding; no colours or fonts outside tokens; every chart through the Plotly template; every number through `format.ts`; every query through `src/data/queries`; `pnpm lint && pnpm test && pnpm build` green before commit; screenshot and compare against the mockup before declaring a panel done.

## 9. Acceptance (v1)

- Balances and Hormuz render from Supabase on `data.kardamow.com`, as-of badges correct, panels grey when stale.
- Panel export at 1200×675 indistinguishable in style from a `core.theme` Python exhibit.
- Lighthouse performance ≥ 85 on Balances; Hormuz map at 60 fps with 2,000 points.
- `pnpm build` output contains no key other than the anon key (`grep -r service_role .next/` empty).
- A pipeline publish followed by `POST /api/revalidate` updates the Balances page within one request.

## 10. Stubs

**33.03 Gas** — EU storage vs band + injection path to 1 Nov target (`seasonal_v`), TTF ladder (`curve_settles`), LNG send-out stacked (`flows`), pipeline flows (`flows`).
**33.04 Curves** — lightweight-charts strip from `curve_settles`, spread ladder from `spreads_v`, prompt-spread history with band, COT positioning from `series_long`.
