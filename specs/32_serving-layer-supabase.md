# Spec 32 — Serving layer (Supabase Postgres, published from the pipelines)

**Status:** draft · **Depends on:** Spec 00 (core schemas), every pipeline spec · **Consumed by:** Spec 33 (Next.js UI).

> Renumbered from the original draft's "Spec 30" — that number is already taken by
> `30_eia-price-coverage.md` (done, live-verified). This is Spec 32; the front-end
> companion is Spec 33.

## 1. Objective

A small, read-optimised Postgres schema on Supabase that holds only what the UI needs, published by the existing Python pipelines at the end of each run. The DuckDB/Parquet lake stays the system of record; Supabase is a serving copy. If the two disagree, the lake wins and the next publish fixes it.

Rules:
- Pipelines write; the UI reads. Nothing else touches `serving.*`.
- Every derived number the UI shows (seasonal bands, deltas, medians, spreads, GRP) is computed in Python with `core.seasonal` and friends, then published as rows. No maths in SQL views beyond filtering and joining.
- Publishing is idempotent: re-running a pipeline for the same period upserts, never duplicates.

## 2. Schema (`serving`)

```sql
create schema if not exists serving;

-- Scalar time series, mirrors core.schemas.ts_long
create table serving.series_long (
  series_id     text not null,
  ts            timestamptz not null,
  value         double precision,
  unit          text,
  geo           text,
  freq          text,            -- 'D','W','M'
  source        text not null,
  revision_date date,
  primary key (series_id, ts)
);
-- NOTE: this draft also declared `create index on serving.series_long (series_id, ts
-- desc)`. It was created, then dropped again in migration
-- 20260909140000_drop_redundant_series_long_index.sql: the primary key above already
-- covers it, since a btree is scanned backwards at effectively the same cost. Measured
-- on the real populated table (463,818 rows) the duplicate cost 38 MB against 41 MB of
-- heap -- ~30% of the whole serving footprint on a 500 MB free tier -- and `explain
-- (analyze)` before/after showed the same plan (Index Scan Backward using
-- series_long_pkey, cost 426.88 vs 426.71). Do not recreate it.

-- Seasonal exhibit rows, one per series per day-of-year, computed by core.seasonal (2020 excluded)
create table serving.seasonal (
  series_id  text not null,
  doy        smallint not null,
  band_min   double precision,
  band_max   double precision,
  median     double precision,
  current    double precision,   -- current year value at this doy, null if not yet
  prior      double precision,   -- prior year
  years      smallint not null,  -- window used, e.g. 5
  unit       text,
  primary key (series_id, doy)
);

-- Directional flows, mirrors core.schemas.flows
create table serving.flows (
  source     text not null,
  from_node  text not null,
  to_node    text not null,
  ts         timestamptz not null,
  period     text not null,      -- 'weekly','monthly'
  value      double precision,
  unit       text,
  mode       text,               -- 'pipeline','seaborne','rail'
  primary key (source, from_node, to_node, ts, period)
);

-- Latest vessel position per MMSI (positions history stays in the lake)
create table serving.vessel_latest (
  mmsi        bigint primary key,
  ts          timestamptz not null,
  geom        geography(point, 4326) not null,
  sog         real, cog real,
  nav_status  text,
  ship_type   text,              -- 'crude','products','lng','other'
  draught     real,
  name        text,
  destination text
);
create index on serving.vessel_latest using gist (geom);

-- GRP (Spec 28)
create table serving.grp_scores (
  theatre   text not null,
  ts        timestamptz not null,
  score     real not null,
  threshold_crossed boolean default false,
  primary key (theatre, ts)
);
create table serving.grp_components (
  theatre   text not null,
  ts        timestamptz not null,
  component text not null,       -- fixed names from Spec 28
  value     real, weight real,
  primary key (theatre, ts, component)
);

-- Curve settlements and precomputed spreads
create table serving.curve_settles (
  root        text not null,     -- 'BRN','WTI','TTF','HH'
  trade_date  date not null,
  contract    text not null,     -- 'BRNX6'
  expiry      date,
  settle      double precision,
  oi          integer,
  source      text,
  primary key (root, trade_date, contract)
);
create table serving.spreads (
  root        text not null,
  trade_date  date not null,
  legs        text not null,     -- 'M1-M2','M1-M12','X6-Z6'
  value       double precision,
  primary key (root, trade_date, legs)
);

-- WPSR at-a-glance rows, one row per report line per week
create table serving.wpsr_lines (
  week_ending   date not null,
  line          text not null,   -- 'crude_ex_spr', 'spr', 'cushing', ...
  label         text not null,
  unit          text,
  value         double precision,
  wow           double precision,
  yoy_pct       double precision,
  vs_median_pct double precision,
  line_order    smallint,
  primary key (week_ending, line)
);

-- Provenance: one row per table per publish
create table serving.publish_log (
  id           bigserial primary key,
  table_name   text not null,
  as_of        timestamptz not null,   -- data as-of (e.g. WPSR week ending, AIS max ts)
  source_note  text,                   -- 'EIA WPSR, Table 4 · week ending 4 Sep 2026'
  row_count    integer,
  pipeline     text,
  git_sha      text,
  published_at timestamptz not null default now()
);
create index on serving.publish_log (table_name, published_at desc);
```

Views (filter/join only):

```sql
create view serving.seasonal_v as select * from serving.seasonal;
create view serving.wpsr_latest_v as
  select * from serving.wpsr_lines where week_ending = (select max(week_ending) from serving.wpsr_lines)
  order by line_order;
create view serving.vessel_latest_v as
  select mmsi, ts, st_y(geom::geometry) as lat, st_x(geom::geometry) as lon, sog, cog, nav_status, ship_type, draught, name, destination
  from serving.vessel_latest;
create view serving.grp_components_v as
  select c.* from serving.grp_components c
  join (select theatre, max(ts) ts from serving.grp_scores group by theatre) l using (theatre, ts);
create view serving.spreads_v as select * from serving.spreads;
create view serving.latest_publish_v as
  select distinct on (table_name) table_name, as_of, source_note, published_at
  from serving.publish_log order by table_name, published_at desc;
```

Migrations live in `supabase/migrations/` and are applied with the Supabase CLI; never hand-edit the schema in the dashboard.

## 3. Publish step (Python)

New module `core/publish.py`:

```python
def publish(table: str, df: pl.DataFrame, *, as_of: datetime, source_note: str, key: list[str]) -> None:
    """Upsert df into serving.<table> on key, then append a publish_log row. Chunked, transactional."""
```

- Uses `psycopg` with the Supabase pooler connection string from `core.settings` (`SUPABASE_DB_URL`, session mode for migrations, transaction mode for publishes).
- Upsert via `COPY` into a temp table then `INSERT … ON CONFLICT DO UPDATE`. Chunks of 50k rows.
- Only whitelisted tables in `serving.*`; refuses anything else.
- After a successful log row, calls `POST {VERCEL_URL}/api/revalidate?tag={table}` with `REVALIDATE_SECRET`. Failure to revalidate is logged, not raised — ISR fallback covers it.
- Every pipeline gets a final `publish()` call per table it feeds. The GRP pipeline publishes `grp_scores` + `grp_components`; the AIS pipeline publishes `vessel_latest` (latest per MMSI only); WPSR publishes `series_long` (its series), `seasonal` (its series, via `core.seasonal`), `wpsr_lines`.

## 4. Access control

- `anon` role: `SELECT` on every `serving.*` table and view via RLS policies `using (true)`. Nothing else.
- `authenticated` role: same for v1; the paid tier later adds a `tier` claim and policies like `using (tier = 'desk' or series_id in (select id from serving.public_series))`.
- Pipelines connect as the database owner through the pooler; the credential lives only in GitHub Actions secrets. The service-role key is never used anywhere.
- `pipelines` never `DROP` or `ALTER`; only migrations do.

## 5. Cadence and staleness

| Table | Publishing pipeline | Cadence | Stale after |
|---|---|---|---|
| `series_long` (EIA weekly) | wpsr | Wed 10:30 ET + 20 min | 8 days |
| `seasonal` | wpsr, gie | on each source run | 8 days / 2 days |
| `wpsr_lines` | wpsr | Wed | 8 days |
| `series_long` (GIE daily) | gie | daily 19:45 CET | 2 days |
| `flows` | flows | weekly | 8 days |
| `vessel_latest` | ais | every 10 min | 30 min |
| `grp_scores`, `grp_components` | grp | 06:00 UTC + on trigger | 26 h |
| `curve_settles`, `spreads` | curve | daily after settle | 2 days |

The UI reads `latest_publish_v` and greys any panel past its stale threshold; thresholds are a constant in `web/src/data/staleness.ts` mirroring this table.

## 6. GitHub Actions

`.github/workflows/publish-*.yml`, one per pipeline, on cron plus `workflow_dispatch`: checkout → `uv sync` → run pipeline → `publish()` → upload lake Parquet as an artifact for 7 days. Secrets: `SUPABASE_DB_URL`, `REVALIDATE_SECRET`, `VERCEL_URL`, plus the source API keys already used.

This is a deliberate departure from `infra/README.md`'s "lake-on-laptop" decision (Spec 13):
that decision was about *pulling* data (needs this laptop's `.env` secrets and local disk),
not about *publishing* an already-pulled DataFrame to a hosted Postgres, which needs no
local state at all. Both can be true at once: pulls stay on Windows Task Scheduler against
the local lake; **publish** runs can live in GitHub Actions once a pipeline has already
written to the local lake in the same job, or (later) be triggered from the local run itself.
Decide per-pipeline in Session 2 of this spec whether `publish()` is called locally right
after the existing scheduled pull, or from a separate Actions job — do not assume Actions
without re-reading this note.

AIS is the exception: a 10-minute cron on Actions is wasteful. Run it as a single long-lived job (6-hour max per run, re-triggered by a schedule) that publishes every 10 minutes, or move it to the reserved Modal/Railway worker if it proves flaky. Decide after two weeks of logs.

## 7. Claude Code sessions

- Session 1 (weekday, 1 h): migration file with §2 schema, apply to a Supabase branch, `supabase gen types`.
- Session 2 (weekend): `core/publish.py` with tests against a local Postgres (docker-compose already exists); wire into the WPSR pipeline; first real publish; verify `wpsr_latest_v` and `latest_publish_v` in the Supabase SQL editor.
- Session 3 (weekend): GIE, GRP, curve pipelines publishing; Actions workflows; revalidate hook.
- Session 4 (weekend): AIS publish; staleness check end to end with the UI.

## 8. Acceptance

- Re-running any pipeline for the same period changes `row_count` in `publish_log` but not the row count in the table.
- `select count(*) from serving.seasonal where doy between 60 and 70` shows no 2020 influence (fixture comparison against `core.seasonal`).
- Anon key can read every `serving.*` view and cannot read anything else, tested with `curl` against PostgREST.
- Free-tier budget: total `serving.*` size under 200 MB after 12 months at the cadences above (vessel history excluded by design).
