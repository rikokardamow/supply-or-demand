# pipelines/ofac — Claude Code Guide

## Real CSV shape, confirmed live (not the vendor's docs alone)
`https://www.treasury.gov/ofac/downloads/sdn.csv` — a full snapshot (not deltas),
19,326 real data rows (plus one trailing blank line at EOF, dropped), no header,
12 fixed positional columns. `-0-` is OFAC's own null placeholder.

**Real `sdn_type` distinct values (4, not the 3 the spec guessed)**: blank/`-0-`
(9,926 — mapped to `"entity"`), `individual` (7,518), `vessel` (1,540), `aircraft`
(342 — not anticipated at all when the spec was written).

## `program` is genuinely multi-valued — a real correction of my own earlier mistake
While first researching this spec, a check for comma/semicolon delimiters in
`program` found none and wrongly concluded the field was always single-valued
(`program: str`, not a list). Only while designing the `geo` resolution for the
events-bridge feature (mapping program → country) did a deeper check reveal the
**real** delimiter: `"] ["` — e.g. `"IRAN] [SDGT] [IRGC] [IFSR"` is four distinct
programs, not one string. **2,905 of 19,326 rows (15%) are genuinely multi-program**;
243 distinct individual program codes exist across the whole file. Confirmed split
logic: `[p.strip("[] ") for p in raw.split("] [")]` correctly turns
`"CUBA] [CUBA-EO14404"` into `["CUBA", "CUBA-EO14404"]` and a plain `"CUBA"` into
`["CUBA"]` (no-op). `SANCTIONS_SCHEMA.programs` is `list[str]`, matching
`events.tags`'s existing list-column precedent — the spec's *original* instinct was
right; my own first-pass verification was the thing that was wrong, corrected before
any code was written against it.

## pandas silently turns a mapped `None` into a float `NaN` — a real, confirmed gotcha
`client.py::fetch_sdn_csv` maps `-0-` to Python `None` via `Series.map()`. Confirmed
live: the resulting column holds a float `NaN`, not `None` (`type(mapped.iloc[0])`
is `float`). This matters because **`NaN` is truthy in plain Python**
(`bool(float("nan"))` is `True`) — a bare `if not value` or `value or default` guard
silently fails to catch it. Caught by a real failing test
(`test_fetch_sdn_csv_maps_null_placeholder_and_entity_type`, initially asserting
`is None` and getting `nan is None` back). Every nullable-field check in
`tagging.py` (`extract_imo`, `is_energy_related`, `resolve_geo`) uses `pd.isna()`
explicitly instead, matching the same pattern already established in
`pipelines/adanos/pull_adanos.py`'s own nullable `sentiment_score` handling.

## IMO extraction — far better coverage than the spec's cautious framing suggested
1,525 of 1,540 real vessel rows (**99%**) have a matching `IMO\s+(\d{7})` pattern in
`remarks`, confirmed against the full real vessel-row set (not just 2-3 named
examples) before writing `extract_imo`.

## `resolve_geo` — vess_flag preferred, program-prefix fallback, blank for thematic-only
Real confirmed distribution from a live pull's own `ofac`-sourced events: `IR` (851),
`RU` (549), blank (365 — thematic-only programs like `SDGT`/`NPWMD` have no country to
resolve, deliberately left blank rather than guessed), `PA`/`CN`/`KP` (vessel-flag
registries), `VE` (48), `CU` (12), `LY` (9), and 10 others — all real, plausible
country codes matching how OFAC sanctions actually concentrate (Iran/Russia/North
Korea dominate; Panama/Liberia/Marshall Islands/Hong Kong are common flags of
convenience for sanctioned vessels).

## Events bridge — the real cross-component connection, confirmed live end-to-end
`events_bridge.py::sanctions_to_events` maps newly-listed, energy-related rows into
the *existing* `events` schema/lake (Spec 09) via the *existing*
`core.storage.write_events` — no new schema, no new overlay component. Confirmed
live: `https://sanctionssearch.ofac.treas.gov/Details.aspx?id=4238` is a real,
working per-entity deep link (its own `lblVesselName` field literally reads "MAR
AZUL", matching that `ent_num`'s real vessel name) — used as the event `url`, not a
generic search-page link.

A real first pull wrote 2,506 energy-related event rows (1,540 vessels are always
`energy_related=True`, plus 966 keyword-matched non-vessel entities) into the
`events` lake alongside GDELT/Guardian/NewsAPI's own rows (1,711 → 4,217 total).
Confirmed live on page 09: the map/feed/table all show the new `source="ofac"` rows
correctly commodity/severity/geo-tagged, with zero changes needed to
`09_events.py`'s own filtering logic. Confirmed live on page 06 (Supply): a real
orange event-overlay marker appears on the Oil-on-Water chart at the pull date,
via the pre-existing `apps/dashboard/components/event_overlay.py` — confirmed
reusable completely as-is.

## Storage — a genuinely different shape from every other pipeline in this project
`sanctions` is a **current-state table** (first_seen/last_seen/status already encode
the diff history), not an accumulating time series like `ts_long`/`flows`/`events`.
`core.storage.write_sanctions_current`/`read_sanctions_current` deliberately don't
use `_write_partitioned` (which assumes a `source=X/year=Y` shape) — a single
overwritten file (`data/lake/sanctions/current.parquet`) is simpler and correct here,
since there's genuinely only one source and no accumulating history to dedupe.
`write_sanctions_snapshot` is a separate, write-only daily audit archive
(`data/lake/sanctions_raw/dt=<date>/part-0.parquet`) per the spec's own requirement —
never read back in this spec's scope.

## Verified (Session A)
A real `pull_ofac.py` run: 19,326 rows fetched and written to the rolling table.
Real `entity_type` distribution matches the live research exactly (entity 9,926,
individual 7,518, vessel 1,540, aircraft 342). 2,506 rows `energy_related=True`.
1,525 of 1,540 vessel rows have a real extracted IMO. All rows `status="active"` on
this first pull (nothing to delist yet). Page 15 verified live in-browser: all four
panels render with real data, plus the cross-page Kardamow-take caption (a real
count of this week's OPEC/OPEC+-tied energy-related listings, pointing to page 06
and the Adanos ticker basket for related context).
