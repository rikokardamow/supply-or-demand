-- Events and OFAC sanctions in the serving layer.
--
-- Spec 32 §2 defined `serving.*` around time series, flows and vessels, and left these
-- two out -- but the lake carries both (3,881 events from GDELT/OFAC/Reddit/StockTwits/
-- Polymarket back to 2018, and 19,365 OFAC SDN entries), and the UI has no way to show
-- an event overlay or a sanctions screen without them.
--
-- Both mirror `core/schemas.py` rather than inventing a shape, so the publisher is a
-- straight copy and the columns mean what they mean everywhere else in this project.

create table serving.events (
  event_id  text primary key,
  ts        timestamptz not null,
  headline  text not null,
  source    text not null,
  url       text,
  tags      text,
  geo       text,
  commodity text,
  severity  smallint
);
create index on serving.events (ts desc);
create index on serving.events (source, ts desc);

-- One row per OFAC SDN entry currently listed. `last_seen` advances on every successful
-- pull whether or not anything changed, which is what makes it a freshness signal
-- (core/freshness.py relies on the same property).
create table serving.sanctions (
  sanction_id    text primary key,
  name           text not null,
  entity_type    text,
  programs       text,
  -- Vessel identity, where the listing is a ship. This project has no AIS positions --
  -- Spec 11 is unbuilt -- so a sanctioned vessel is known here by identity, never by
  -- location, and the UI must not imply otherwise.
  call_sign      text,
  vess_type      text,
  vess_flag      text,
  vess_owner     text,
  imo            text,
  remarks        text,
  energy_related boolean,
  status         text,
  first_seen     timestamptz,
  last_seen      timestamptz
);
create index on serving.sanctions (energy_related, last_seen desc);
create index on serving.sanctions (imo) where imo is not null;

-- Read-only for anon, exactly like every other serving table (Spec 32 §4).
alter table serving.events enable row level security;
alter table serving.sanctions enable row level security;

create policy "anon and authenticated can read events" on serving.events
  for select to anon, authenticated using (true);
create policy "anon and authenticated can read sanctions" on serving.sanctions
  for select to anon, authenticated using (true);

grant select on serving.events to anon, authenticated;
grant select on serving.sanctions to anon, authenticated;

-- Latest events, for an overlay that wants only the recent tail.
create view serving.recent_events_v with (security_invoker = true) as
  select event_id, ts, headline, source, url, tags, geo, commodity, severity
  from serving.events
  where ts >= now() - interval '180 days'
  order by ts desc;

-- Sanctioned vessels: the energy-relevant subset that carries a real IMO number.
create view serving.sanctioned_vessels_v with (security_invoker = true) as
  select sanction_id, name, vess_type, vess_flag, vess_owner, call_sign, imo,
         programs, status, first_seen, last_seen
  from serving.sanctions
  where imo is not null and imo <> ''
  order by last_seen desc;

grant select on serving.recent_events_v to anon, authenticated;
grant select on serving.sanctioned_vessels_v to anon, authenticated;
