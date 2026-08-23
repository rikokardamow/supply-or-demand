# pipelines/eia — Claude Code Guide

## Route/facet pattern
EIA API v2 requests: `GET https://api.eia.gov/v2/{route}/data/` with query params
`api_key`, `frequency`, `data[0]=value`, `facets[series][]=<series_id>` (repeated once per
series — `requests` does this automatically when given a `list[str]` param value),
`sort[0][column]=period`, `sort[0][direction]=desc`, `offset`, `length`.

## Pagination
Max `length` per page is **5,000 rows**. Loop, incrementing `offset` by 5,000, until a page
returns fewer than 5,000 rows — don't rely on the response's `total` field, it has been
inconsistent across EIA routes.

## revision_date
EIA v2 payloads carry no per-row revision/last-updated timestamp. `EIAClient.get_series`
stamps `revision_date` with the UTC time of the pull itself. If a route is later found to
expose real vintages, prefer that over ingestion time and update this note.

## Secrets
Never log or print the full request URL or params dict — both contain `api_key`. If you need
to debug a request, log the URL with the `api_key` param redacted first.

**Response body gotcha**: the EIA API echoes the full request (including `api_key` in
plaintext) back inside the JSON response body itself, under `response.request.params.api_key`.
`filter_query_parameters` in vcrpy only scrubs the request URI — it does **not** touch this.
`tests/conftest.py`'s `vcr_config` has a `before_record_response` hook that scrubs this field
before a cassette is ever written to disk. Any new cassette-recording test must use that same
`vcr_config` fixture (module-scoped, picked up automatically via `@pytest.mark.vcr`) — do not
record against this API with a bare vcrpy config that skips it.

## Discovering series codes — don't guess
`GET https://api.eia.gov/v2/{route}/facet/series` (same `api_key` param, no other params
needed) lists every series code + description available under that route. Use this instead
of guessing a code from a name — it's how the gross-inputs-by-PADD codes below were found
(the spec text named the concept but not the codes) and how each route below was confirmed
before use.

## `geo` field mapping
The EIA response has **no `area` key** — only `area-name` (e.g. `"U.S."`, `"PADD 1"`) and
`duoarea`. `EIAClient.get_series` maps `area-name` through `_normalise_geo()`:
`"U.S."` → `"US"`, `"PADD 1"` → `"PADD1"` (matches `core/schemas.py`'s `geo` convention).
Earlier code read `row.get("area", "")`, which silently produced an empty `geo` for every
row — fixed in Spec 01 Session A; re-running any pull backfills it via `write_ts_long`'s
revision-based de-dup.

**Known quirk**: `W_EPC0_SAX_YCUOK_MBBL` (Cushing, OK) comes back with `area-name: "NA"` from
EIA itself — Cushing is a sub-regional hub, not a PADD or national aggregate, so it doesn't
fit either bucket. This is the real API response, not a mapping bug; `geo` is left as `"NA"`
for it rather than guessing a PADD assignment EIA doesn't provide.

## Series used so far
Route `petroleum/stoc/wstk` (weekly stocks):
- `WCESTUS1` — US crude oil stocks excluding SPR.
- `W_EPC0_SAX_YCUOK_MBBL` — Cushing, OK crude oil stocks.
- `WCSSTUS1` — US crude oil stocks in the SPR.
- `WGTSTUS1` — US total gasoline stocks.
- `WDISTUS1` — US distillate fuel oil stocks.
- `WTESTUS1` — US ending stocks excl. SPR, crude oil and petroleum products combined
  (1.245 Bn bbl as of 2026-08-14 — matches a "Bn bbl"-scale chart, not "MBBL"-scale).

Route `petroleum/pnp/wiup` (weekly refinery utilisation & gross inputs):
- `WPULEUS3` — US % utilisation of refinery operable capacity.
- `W_NA_YUP_R10_PER` .. `R50_PER` — PADD1-5 % utilisation.
- `WGIRIUS2` — US gross inputs to refineries.
- `WGIRIP12` / `P22` / `P32` / `P42` / `P52` — PADD1-5 gross inputs.

Route `petroleum/cons/wpsup` (weekly product supplied — demand proxy):
- `WRPUPUS2` — US total petroleum products.
- `WGFUPUS2` — US finished motor gasoline.
- `WDIUPUS2` — US distillate fuel oil.
- `WKJUPUS2` — US kerosene-type jet fuel.

Route `petroleum/move/wkly` (weekly imports):
- `WCEIMUS2` — US commercial crude oil imports excluding SPR.

Route `petroleum/sum/sndw` (weekly national supply/demand summary):
- `WCRRIUS2` — US refiner net input of crude oil ("refinery demand").
- `WCRFPUS2` — US field production of crude oil.
- `WCREXUS2` — US exports of crude oil.
- `WTTEXUS2` — US exports of crude oil and petroleum products combined.

Inter-PADD crude movements (monthly, `flows` schema, not `ts_long`):
- Routes `petroleum/move/pipe` (mode=`pipeline`), `petroleum/move/tb` (mode=`tanker_barge`),
  `petroleum/move/rail` (mode=`rail`). Series IDs follow **inconsistent conventions across
  routes and even within a route** (`MCRMPP2P31`, `M_EPC0_TNR_R40-R10_1`,
  `ESM_EPC0_RAIL_R20-R30_MBBL` are all real IDs) — do not derive IDs from a pattern.
  `pipelines/eia/corridors.py` discovers valid main-PADD-to-PADD crude corridors by
  **parsing the human-readable `name` field** from `list_series()` (the facet listing)
  against a fixed regex, not by guessing IDs. This also naturally excludes PADD sub-regions
  (1A/1B/1C) and series covering "Crude Oil and Petroleum Products" combined, which don't
  match the crude-only pattern.
- `petroleum/move/ptb` (combined pipeline+tanker+barge+rail total) exists but is **not**
  pulled — flows needs a single `mode` per row, and pipe/tb/rail already sum to the same
  totals with a real mode value, so there is no need for the aggregate route.

All confirmed live against the real API.

## Plotly geo-map gotcha (apps/dashboard/components/padd_map.py)
`fig.add_annotation(..., axref="geo", ayref="geo", ...)` does **not** work in the installed
plotly version (5.24.1) — `xref`/`yref` accept `"geo"` (the annotation's anchor point can be
geo-referenced) but `axref`/`ayref` (the arrow-tail position) only accept `"pixel"` or a
cartesian x-axis ref. Confirmed by triggering the actual `ValueError` live, not assumed.
Directional flow lines on a `Scattergeo` map are drawn instead as `mode="lines"` traces plus
a separate rotated `marker={"symbol": "triangle-up", "angle": bearing}` trace positioned
partway along the line — `Scattergeo`'s marker `angle` property does work.
