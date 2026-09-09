-- Spec 32 Session 1: serving schema for the Next.js UI (Spec 33).
-- The DuckDB/Parquet lake remains the system of record; this is a read-optimised
-- serving copy, published by the Python pipelines via core/publish.py (not built yet).
-- See specs/32_serving-layer-supabase.md.

create extension if not exists postgis with schema extensions;

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
create index on serving.series_long (series_id, ts desc);

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

-- Views (filter/join only -- no maths; see Spec 32 §1)
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

-- Access control (Spec 32 §4): anon/authenticated get SELECT only, on every serving
-- object, via RLS -- nothing else. Pipelines publish through the pooler as the
-- database owner (a service credential, never the anon/authenticated roles), which
-- bypasses RLS as table owner, so no write policy is needed here.
grant usage on schema serving to anon, authenticated;

alter table serving.series_long enable row level security;
alter table serving.seasonal enable row level security;
alter table serving.flows enable row level security;
alter table serving.vessel_latest enable row level security;
alter table serving.grp_scores enable row level security;
alter table serving.grp_components enable row level security;
alter table serving.curve_settles enable row level security;
alter table serving.spreads enable row level security;
alter table serving.wpsr_lines enable row level security;
alter table serving.publish_log enable row level security;

create policy "anon and authenticated can read series_long" on serving.series_long
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read seasonal" on serving.seasonal
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read flows" on serving.flows
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read vessel_latest" on serving.vessel_latest
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read grp_scores" on serving.grp_scores
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read grp_components" on serving.grp_components
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read curve_settles" on serving.curve_settles
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read spreads" on serving.spreads
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read wpsr_lines" on serving.wpsr_lines
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read publish_log" on serving.publish_log
  for select to anon, authenticated using (true);

grant select on all tables in schema serving to anon, authenticated;
