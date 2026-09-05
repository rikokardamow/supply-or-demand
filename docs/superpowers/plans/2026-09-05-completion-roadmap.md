# Energy Dashboard — Full Integration Completion Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase plan task-by-task. This file is the *route*; each phase has (or gets) its own task-level plan in this directory.

**Goal:** Take the repo from "Specs 00–20 built" to "every spec in `specs/` integrated, orchestrated, tested and green", including the Spec 28 GRP module adapted to this repo's real stack.

**Architecture:** One substrate throughout — DuckDB + Parquet lake written by `pipelines/`, read by a Streamlit multipage app, scheduled by `infra/run_scheduled.py`. No Postgres, no FastAPI, no Grafana and no Docker is introduced. Spec 28 is adapted onto that substrate exactly as `weather-module-spec.md` was (see `README.md:766`, `CHANGELOG.md:247`, `pipelines/weather/CLAUDE.md:221`).

**Tech Stack:** Python 3.12, uv, pandas, duckdb, pyarrow, plotly, streamlit, pydantic-settings, statsmodels, ruptures, arch, scipy. Lint ruff, types mypy, tests pytest + vcrpy cassettes.

**Spec:** `specs/00_INDEX.md`, `specs/00_TRADING_CONVENTIONS.md`, `specs/21_*`–`specs/27_*`, `specs/28.00`–`specs/28.11`, `specs/11_ais-vessels.md`, `specs/12_flights.md`

---

## Global Constraints

Copied verbatim from `CLAUDE.md` and `specs/00_TRADING_CONVENTIONS.md`. Every task in every phase plan implicitly includes this section.

- Never print, log, or commit API keys. All secrets via `core.settings` (pydantic-settings) from `.env`.
- Pipelines write to `data/` in canonical schemas. Dashboard pages READ the lake, never call APIs.
- All scalar time series conform to `ts_long`; directional data to `flows`. See `core/schemas.py`.
- Seasonal maths (median/range/corridor) ALWAYS exclude 2020. Use `core.seasonal` — never reimplement.
- Charts use `core.theme` (Kardamow house style). No ad-hoc colours or styling.
- British English in all prose, labels, and docstrings.
- Small, typed, tested functions. **Ask before adding a dependency or changing a schema.**
- End every session green: `pytest` passes, `ruff check .` clean, work committed.
- Every chart section wrapped in `apps.dashboard.components.card.card(title)`. Maps use `go.Scattermapbox` with `"open-street-map"` — never `go.Scattergeo`.
- Analytics live in flat `core/<topic>.py` modules; ingestion in `pipelines/`. No new package trees.
- Only four schemas exist: `TS_LONG_SCHEMA`, `FLOWS_SCHEMA`, `EVENTS_SCHEMA`, `SANCTIONS_SCHEMA`. `vessel_positions` / `vessel_static` are named in `CLAUDE.md` but **do not exist in `core/schemas.py`** — Phase 5 creates them.
- Every model card shows window / refit / OOS status / exceptions / break date. Published literature benchmarks shown beside repo estimates with the deviation.
- Spreads never from back-adjusted series.

---

## Where the repo actually is

| Spec | State | Evidence |
|---|---|---|
| 00–10, 13–17 | **Built** | `pipelines/{eia,gie,entsog,entsoe,eirgrid,gridstatus_iso,opec_momr,jodi,baker_hughes,weather,news,macro,ofac,adanos,cftc}`, pages 01–15, `infra/run_scheduled.py` |
| 11 AIS vessels | **Not built** | no `pipelines/ais`, no vessel schema in `core/schemas.py` |
| 12 Flights (OpenSky) | **Not built** | no `pipelines/flights` |
| 18 curve / 19 fundamentals / 20 cracks | **Built** | `core/curve.py`, `core/fundamentals.py`, `core/cracks.py`, `core/vecm.py`, pages 18–20 |
| 21–27 | **Not built** | none of `core/{systematic,backtest,strategies,risk,risk_desk,macro_signals,predictive,vol,cso,structures,arb,freight,gas_analytics,gas_strategies,journal,ledger}.py` exist; pages stop at `20_cracks.py` |
| 28.00–28.11 | **Not built, and specced against the wrong stack** | see below |

Working tree is clean, `ruff check .` passes, current branch `feat/systematic-engine`.

---

## The Spec 28 adaptation contract

Spec 28 was written against a Postgres 16 + pgvector / FastAPI / Grafana / docker-compose platform and repeatedly says "the repo's existing" for things that do not exist here. Decision (5 September 2026): **adapt, do not build the platform.** This table is the contract. It is the single most important artefact in this roadmap, because no spec file contains it.

| Spec 28 construct | Adapted target in this repo |
|---|---|
| Postgres schema `grp`, DDL in `grp/store/migrations/0001_grp_schema.sql` (28.02) | Parquet state tables under `data/lake/grp/`, schemas in `core/schemas.py` following the `SANCTIONS_SCHEMA` precedent (a state table, **not** `_write_partitioned`) |
| `grp.scores` rows | `ts_long` series `grp.gulf.score`, `.escalation`, `.taco`, `.airspace`, `.physical`, `.crowded` written by `write_ts_long(df, source="grp")` |
| pgvector `vector(384)` + `<=>` cosine | The spec's **own documented fallback** (28.02 §1, 28.03 §6): store embeddings as a float32 list column, compute cosine in Python over the dedup window only |
| PostGIS `geometry(Polygon,4326)` | The spec's own fallback: `bbox` as JSON + shapely. PostGIS is optional in the spec's own v1 anyway |
| `api/routers/grp.py`, `api/models/grp.py`, `X-GRP-TOKEN` write endpoints (28.09) | **Dropped.** Page `28_grp.py` reads the lake directly (rule 2). The two write endpoints become Streamlit forms on the review table — no network surface, so no write token exists to leak |
| Grafana dashboard `grp.json`, 10 panels, alerts (28.10) | `apps/dashboard/pages/28_grp.py`: one `card()` per panel using `core/theme.py` primitives; panel 8 geomap → `go.Scattermapbox` open-street-map reusing `components/news_map.py`; the alert engine → `pipelines/grp/alerts.py` writing `events` rows surfaced by the existing `components/event_overlay.py` |
| `docker-compose.yml`, `grp/jobs/scheduler.py` APScheduler, `make` targets (28.11) | A new `grp_fast` cadence in `infra/run_scheduled.py`'s `CADENCE_GROUPS`, registered by `infra/register_tasks.ps1`. The `Makefile` gains no Docker targets |
| Alembic / `make migrate` | None. Parquet schema evolution as the repo already does it |
| Railway mapping (28.11 §6, Phase 4) | Deferred to Phase 7. Note `railway.toml` is **stale** — it starts `src/kardamow/app/main.py` and `scripts.run_ingestors`, neither of which exists |
| "Reads the repo's `eia` schema" (28.06) | `core.storage.read_ts_long([...])` against real `eia.*` series IDs — verify each against the live lake first, per `00_TRADING_CONVENTIONS.md`'s own "checked live, not assumed" rule |
| "Brent curve from `markets`" (28.07) | `core/curve.py` plus the `fut.*` / `derived.curve.*` series Spec 18 already writes |
| CFTC COT (28.07) | `pipelines/cftc/` already exists — reuse, do not duplicate |
| NewsAPI / WorldNews / GDELT ingestion, dedup, classify (28.03) | **Extend `pipelines/news/`**, which already has `client.py`, `newsapi_client.py`, `guardian_client.py`, `dedup.py`, `tagging.py`, `translate.py` and their tests. Spec 28.06 states the rule itself: "Do not duplicate ingestion" |
| `sentence-transformers` MiniLM embeddings, pre-baked into a Docker layer | **New dependency — needs approval (rule 7).** First try `pipelines/news/dedup.py`, which already passes `tests/test_news_dedup.py`. Only add the model if that measurably fails GRP's dedup acceptance criteria |
| Anthropic LLM classifier (28.03) | Keep as specced — `anthropic>=0.40` is already a dependency |
| AISStream websocket service (28.05) | Requires Spec 11, which is unbuilt → Phase 5 |
| FAA NOTAM + OpenSky (28.04) | Requires Spec 12, which is unbuilt → Phase 5 |

**Phase 0 writes this table into `specs/28_ADAPTATION.md`**, so every later session reads it the way Specs 18–27 read `00_TRADING_CONVENTIONS.md`. Sessions must not re-litigate it.

---

## The route

Dependency order comes from `specs/00_INDEX.md` ("18 → 19 → 21 → 22, then 20 / 24 / 25 / 26 in any order, 23 and 27 any time after 18") plus three constraints read out of the spec bodies:

- Spec 21 Session B builds `core/backtest.py`, which 20, 24, 25, 26 and 27 all import. **21 is the keystone.**
- Spec 21 ships a 63-day realised-vol fallback that Spec 22 replaces; 24 and 26 need Spec 22's `realised_vol` / `hedge_effectiveness`. **22 before 24 and 26.**
- Spec 27's `log_signal_trade()` is called by 20/21/24/25/26. **27 after them.**

| Phase | Content | Sessions | Gate to pass |
|---|---|---|---|
| 0 | Commit specs 28; write `specs/28_ADAPTATION.md`; confirm green | 1 | `ruff` + `pytest` green, tree committed |
| 1 | **Spec 21** systematic engine | A, B, C | `core/backtest.py` exists and the CARRY_1_13 benchmark card renders |
| 2 | **Spec 22** risk engine | A, B, C | pass/fail matrix live, HS shown failing; 21's vol fallback removed |
| 3 | **Specs 23, 24, 25, 26** (fan out) | 12 | four pages live, all registered with orchestration |
| 4 | **Spec 27** journal / playbook / ledger | A, B, C, D | `log_signal_trade` wired into 21's daily positions step |
| 5 | **Specs 11 + 12** AIS and flights | ~5 | vessel schemas in `core/schemas.py`; both pipelines cassette-tested |
| 6 | **Spec 28 GRP**, adapted | ~8 | GRP score in the lake on a 30-minute cadence; page 28 live |
| 7 | Integration hardening | 2 | orchestration audit, CI, `railway.toml`, docs |

Total ≈ 34 sessions. At the `00_INDEX.md` budget (3–4 h weekends, ≤1 h some weekdays) that is roughly four to five months, and phases 3 and 5 are the ones that parallelise if you want to compress it.

---

## Phase detail

### Phase 0 — Gate (one short session)

Not optional: every later phase reads `specs/28_ADAPTATION.md`, and the 12 spec files are currently untracked, so nothing references them yet.

1. `git add specs/28.*.md && git commit` — get the spec pack under version control before anything is built against it.
2. Create `specs/28_ADAPTATION.md` from the contract table above, plus a short "why" paragraph citing the weather-module precedent.
3. Add a line to `specs/00_INDEX.md`'s build order for 28, and for the fact that 11 and 12 are still open.
4. Confirm `ruff check .` and `pytest --record-mode=none` are green, commit.

### Phase 1 — Spec 21, Systematic Strategies Engine

Detailed task-level plan: **`docs/superpowers/plans/2026-09-05-spec-21-systematic-engine.md`** (written; execute this next).

Keystone phase. Session A is pure maths with no lake I/O and is the cleanest possible start; Session B produces `core/backtest.py`, which everything downstream imports; Session C is the page. Branch `feat/systematic-engine` already exists.

### Phase 2 — Spec 22, Risk Engine

Three sessions per the spec. Session A is the GARCH-MIDAS-EVT model in scipy — the single hardest numerical task in the whole roadmap, and the one most worth its own worktree and a long review. Before designing the MIDAS inputs, confirm which monthly macro series Spec 10 already holds (the spec says so explicitly, and `00_TRADING_CONVENTIONS.md` has a verified series-ID section for exactly this).

On completion, delete Spec 21's realised-vol fallback and repoint `core/systematic.py` at `core.risk.realised_vol`. That deletion is a task, not a note — leaving both in place is how the two silently diverge.

### Phase 3 — Specs 23, 24, 25, 26 (fan out)

These four are mutually independent. Each gets its own worktree via `superpowers:using-git-worktrees` and its own plan generated at phase entry. Ordering within the phase is by risk:

- **25 Freight** first — all-manual data, a checked-in synthetic fixture CSV, no new API. Lowest risk, and it warms up `core/backtest.py` usage.
- **23 Macro signals** next — needs new FRED IDs confirmed live before any modelling.
- **26 Gas analytics** — needs Spec 22's `hedge_effectiveness`; otherwise pure analytics over data already in the lake.
- **24 Vol & options** last of the four — it is the only one that extends *both* futures clients to option chains and CSOs, so it can break Spec 18's daily pull.

### Phase 4 — Spec 27, Journal / Playbook / Ledger

Four sessions. Goes after Phase 3 because Session B wires `log_signal_trade` into the daily positions step of 21 and into the strategies of 20/24/25/26 — wiring into strategies that do not exist yet means rework. Session A introduces four new state-table schemas, which is a `CLAUDE.md` rule-7 schema change: confirm before writing.

### Phase 5 — Specs 11 and 12 (AIS, flights)

Promoted here from "do last" because GRP's `physical` component (28.05) and `airspace` component (28.04) are two of GRP's four inputs, and both are blocked on these. Spec 11 also needs `vessel_positions` and `vessel_static` added to `core/schemas.py` — they are listed in `CLAUDE.md` as canonical but do not exist in code.

If you want GRP sooner, the descope is: build 28 with `escalation` + `taco` + `physical`-from-EIA only, renormalise the weights in `config/model.yaml`, and land `airspace` and the AIS half of `physical` after Phase 5. The spec's formula is config-driven and versioned precisely so this is legal — bump `model_version`.

### Phase 6 — Spec 28 GRP, adapted

Roughly eight sessions, following the spec pack's own order but against the adaptation contract:

1. Config files (28.01) plus lake schemas (28.02 adapted) — `config/theatre_gulf.yaml`, `model.yaml`, `sources.yaml`, `alerts.yaml`, `core/grp.py` state tables.
2. News ingestion, dedup, classify (28.03) — as an **extension of `pipelines/news/`**.
3. Physical confirmation from EIA (28.06) — reuse `pipelines/eia`; the one permitted edit outside the module is adding missing EIA series there.
4. Positioning (28.07) — reuse `pipelines/cftc` and `core/curve.py`.
5. Airspace (28.04) and maritime (28.05) — on top of Phase 5.
6. TACO / escalation / composite (28.08) — the scoring core; pure functions, heavily tested.
7. Page `28_grp.py` plus the exhibits and alert engine (28.10 adapted).
8. Orchestration: `grp_fast` cadence, `infra/register_tasks.ps1`, cassette tests.

### Phase 7 — Integration hardening

1. Orchestration audit: every spec's DoD says "registered with Spec 13". Walk `CADENCE_GROUPS` against every `pipelines/*/pull_*.py` and `pipelines/derived/*.py` and fix the gaps, preserving the load-bearing intra-group ordering already commented there.
2. CI: `ci.yml` currently runs ruff, mypy and cassette-only pytest. Add the placeholder env vars any new source needs, and decide whether `tests/test_pages_browser.py` runs in CI or stays local.
3. `railway.toml`: either fix the stale paths (`apps/dashboard/app.py`, `infra.run_scheduled`) or delete it. Leaving a deploy config that points at non-existent modules is worse than having none.
4. `README.md`, `CHANGELOG.md`, `specs/00_INDEX.md` final pass.

---

## Definition of Done (roadmap)

- [ ] Every spec in `specs/` is either built or carries an explicit written descope decision **inside its own spec file** (the `00_INDEX.md` rule).
- [ ] `ruff check .` clean, `mypy core pipelines infra` clean, `pytest --record-mode=none` green.
- [ ] Every pipeline and derived entrypoint appears in `infra/run_scheduled.py`'s `CADENCE_GROUPS`.
- [ ] Every page renders under `tests/test_pages_smoke.py` and `tests/test_pages_browser.py`.
- [ ] `specs/28_ADAPTATION.md` exists and every 28.x deviation traces to a row in it.
- [ ] `README.md` and `CHANGELOG.md` updated; `railway.toml` fixed or removed.
