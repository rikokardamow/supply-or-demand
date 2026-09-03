# Spec 15 — OFAC SDN Sanctions List

**Est. 3–4 h · Prereq: Spec 00. Independent data source — overlays onto Spec 11 (AIS vessels) once built.**

## Objective & alpha question
Track the US Treasury's Specially Designated Nationals (SDN) list as a day-over-day diffable
dataset, tagged for energy relevance (crude/product tankers, energy entities, oil-producing-state
individuals). Question: *which newly-sanctioned entities/vessels touch the energy complex, and does
a sanctioned tanker's flag/owner show up in AIS traffic (Spec 11) once that lands?*

## Data sources
1. **OFAC SDN full list (CSV)** — free, no key. Primary:
   `https://www.treasury.gov/ofac/downloads/sdn.csv`. Confirmed-live mirrors (byte-identical,
   useful as fallbacks if the primary host is slow/down):
   `https://sanctionslistservice.ofac.treas.gov/api/download/sdn.csv` and
   `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV`.
2. OFAC publishes a **full snapshot**, not deltas — every pull is the entire current list
   (confirmed live: 19,322 rows / 5,670,063 bytes as of 2 Sept 2026). Day-over-day additions/
   removals must be computed by diffing snapshots (see Transformations).

## Data model
The raw CSV is confirmed live to have **no header row** and 12 fixed positional columns:
`ent_num, sdn_name, sdn_type, program, title, call_sign, vess_type, tonnage, grt, vess_flag,
vess_owner, remarks`. `-0-` is OFAC's own literal placeholder for "no value" — treat it as null,
not a real string, when parsing.

New canonical schema `sanctions` (list-typed `programs`, matching `events.tags`'s existing
precedent for a list column in this lake):
- `sanction_id` (str, = `ent_num`)
- `name` (str, = `sdn_name`)
- `entity_type` (str, = `sdn_type` — confirmed live values include at least `individual`,
  `-0-`/blank for corporate entities, and `vessel`; enumerate the real distinct values live
  before finalising, don't assume only these three)
- `programs` (`list[str]`) — the `program` field's delimiter is not yet confirmed at spec-writing
  time; check live during implementation (semicolon vs comma vs single-value) before writing the
  split logic, per this project's "don't guess schemas" rule
- `vess_type`, `vess_flag`, `vess_owner`, `call_sign` (str, nullable — populated only for
  `entity_type == "vessel"` rows; confirmed live e.g. `Vess_type="Tug"`, `Vess_flag="Cuba"`)
- `remarks` (str, nullable) — free text; confirmed live that an IMO number sometimes appears here
  as e.g. `"Vessel Registration Identification IMO 7406784"` rather than in a dedicated column
- `first_seen`, `last_seen` (datetime) — set/updated by the diff logic below, not present in the
  raw CSV
- `status` (str: `active` / `delisted`) — `delisted` when a `sanction_id` present in a previous
  snapshot is absent from the latest one
- `energy_related` (bool) — see Transformations

## Transformations
- **Snapshot diff**: each pull writes the full current list to
  `data/lake/sanctions/dt=<pull_date>/*.parquet` (dated partitions, since OFAC gives no revision
  history of its own) AND upserts into a rolling `sanctions` table keyed by `sanction_id`:
  a `sanction_id` newly seen gets `first_seen = pull_date`; one seen in a previous pull but
  missing from the latest gets `status = "delisted"`, `last_seen` = the last pull date it appeared.
- **Energy/vessel tagging**: reuse `pipelines/news/tagging.py`'s keyword-dictionary pattern (do
  not reimplement) — match `name`/`remarks`/`program` against an energy/vessel keyword set
  (tanker, crude, petroleum, shipping, oil, gas, refinery, National Iranian Oil Company, etc.) to
  set `energy_related`. Any `entity_type == "vessel"` row is `energy_related = true`
  unconditionally regardless of keyword match (a sanctioned vessel is inherently shipping-relevant
  to this dashboard even if its cargo type isn't stated).
- **IMO extraction**: a small regex over `remarks` (`IMO\s+(\d{7})`) populates an optional `imo`
  column when present — needed for the Spec 11 cross-reference stretch goal below. Confirmed live
  this pattern matches real rows (e.g. `MAR AZUL`, `EBANO`). Not every vessel row has one; leave
  null rather than guessing.

## Visualisation spec (page `15_sanctions.py`)
1. Full current SDN table (filterable by program, entity type, energy-related), most-recently-
   `first_seen` first.
2. "Newly listed this week" panel — rows where `first_seen` falls in the trailing 7 days,
   energy-related subset highlighted.
3. Vessel watchlist — `entity_type == "vessel"` rows as a table: name, flag, owner, tonnage,
   programs, IMO (if extracted).
4. Delisted panel — rows that flipped to `status = "delisted"` in the latest diff (a sanction
   being lifted is itself informative for energy-complex risk premia).

## Sessions

### Session A (weekday, 1–1.5 h) — CSV client + snapshot diff
> Read NOTES.md, specs/15_ofac-sanctions.md. Build `pipelines/ofac/client.py` (fetch + parse the
> positional CSV, confirm the real `program` delimiter and `sdn_type` distinct values live before
> finalising the schema), `core/schemas.py::SANCTIONS_SCHEMA`/`SanctionsRecord`, and the
> first-seen/last-seen/status diff logic against the rolling table. Cassette test using a captured
> real CSV sample. Acceptance: a second pull with one row removed from the fixture correctly flips
> that row to `delisted` without duplicating other rows.

### Session B (weekday, 1–1.5 h) — tagging + page
> Wire in `energy_related` tagging (reusing `pipelines/news/tagging.py`'s pattern) and IMO
> extraction; build page 15 with the four panels above. Daily entrypoint `pull_daily.py`.

## Definition of Done
- OFAC SDN ingesting via the diffable snapshot model; `sanctions` schema validated and tested;
  page 15 live with all four panels; energy/vessel tagging tested against real confirmed examples
  (Cuba-flagged tugs/cargo vessels). Tests green.

## Stretch
- Cross-reference `vess_flag`/`vess_owner`/extracted `imo` against Spec 11's AIS `vessel_static`
  table once that spec is built, to flag sanctioned vessels currently broadcasting AIS positions.
