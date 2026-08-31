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

## Spec 05 Session A — natural gas storage, and a route where area-name is useless

Route `natural-gas/stor/wkly` (weekly working gas storage) — 8 series confirmed live via
`list_series()` (the spec only names the Lower-48 code plus "regional... incl.
salt/non-salt" generically):

| Series ID | Region | `duoarea` | `process` |
|---|---|---|---|
| `NW2_EPG0_SWO_R48_BCF` | Lower 48 (L48) | R48 | SWO |
| `NW2_EPG0_SWO_R31_BCF` | East | R31 | SWO |
| `NW2_EPG0_SWO_R32_BCF` | Midwest | R32 | SWO |
| `NW2_EPG0_SWO_R33_BCF` | South Central (aggregate) | R33 | SWO |
| `NW2_EPG0_SSO_R33_BCF` | South Central — Salt | R33 | SSO |
| `NW2_EPG0_SNO_R33_BCF` | South Central — Nonsalt | R33 | SNO |
| `NW2_EPG0_SWO_R34_BCF` | Mountain | R34 | SWO |
| `NW2_EPG0_SWO_R35_BCF` | Pacific | R35 | SWO |

Cross-checked live: Salt (248 BCF) + Nonsalt (813 BCF) = South Central aggregate (1061 BCF)
exactly for the same period — the three R33 series are additive, not overlapping.

**`area-name` is the literal string `"NA"` for every row on this route, confirmed live** —
not a genuine missing-value case like Cushing's real `"NA"` (see above), this route simply
never populates the field regardless of region. `EIAClient.get_series`'s existing
`_normalise_geo(area-name)` path would silently collapse all 8 series to `geo="NA"`. Fixed
by adding an optional `geo_map: dict[str, str] | None = None` parameter to `get_series` —
when given, `geo` is looked up per `series_id` instead of derived from `area-name`. `None`
(the default) leaves every other route's existing behaviour untouched.
`pipelines/eia/pull_gas_storage.py`'s `STORAGE_GEO_MAP` is the map for this route. Reach for
`geo_map` on any future route where `area-name` turns out to be similarly unusable — check
first via `_fetch_rows`/`list_series` rather than assuming `_normalise_geo` is always enough.

16 years of weekly history available (2010-01-01 onward, 869 rows for L48 alone as of
2026-08-21) — ample for `core.seasonal.seasonal_stats`'s 5-year corridor.

Page `05_us_gas_power.py` (Session A scope only — ISO tabs and production/exports are later
sessions): L48 headline worm chart + a 7-region small-multiples grid, both via
`core.seasonal.seasonal_stats` + `core.theme.seasonal_range_chart` — the same pattern
already used by `01_us_padd.py` (petroleum) and `02_gas_storage.py` (GIE), no new chart
primitive needed. Acceptance criterion met: the lake's latest L48 value (3184 BCF,
2026-08-21) matched a fresh, independent `EIAClient.get_series` call exactly.

## Session C — production/exports, and a correction to the spec's named LNG export route

`pull_production_exports.py` pulls two national monthly series: `natural-gas/prod/sum`'s
`N9070US2` ("U.S. Dry Natural Gas Production", MMcf) and `natural-gas/sum/lsum`'s
`N9133US2` ("Liquefied U.S. Natural Gas Exports", MMcf). Both `area-name`-normalise to
`geo="US"` cleanly (unlike the storage route above) — no `geo_map` needed here.

**The spec's own named route for LNG exports, `natural-gas/move/poe2`, doesn't have a
usable national total — confirmed live, not assumed.** That route (and `natural-gas/
move/expc`, checked as an alternative) only publish **per-destination-country** series
(e.g. `NGM_EPG0_ENG_NUS-NCA_MMCF` = "...to Canada"). Summing every "U.S. Liquefied Natural
Gas Exports to <country>" series found under `poe2` (17 series, confirmed via
`list_series()`) totalled only ~88,544 MMcf for the latest month — a small fraction of the
real figure. `natural-gas/sum/lsum` (a genuine summary route, discovered by walking
`GET /v2/natural-gas/` → `sum` → its sub-routes rather than guessing) has the real,
pre-aggregated national total instead: confirmed live via an exact cross-check —
`N9132US2` (pipeline exports) + `N9133US2` (LNG exports) == `N9130US2` (combined total
exports), all three from the same route, matching to within EIA's own rounding (1 MMcf on
~816,601). `N9133US2` alone (~502,812 MMcf/month ≈ 16.8 Bcf/d for the latest month) is a
plausible real-world US LNG export rate; the `poe2` route's per-country sum was not.
`tests/test_eia_client.py::test_lng_exports_cross_checks_against_pipeline_plus_total`
encodes this check as a regression test.

**Feedgas** (gas consumed at LNG liquefaction facilities before export) has no distinct EIA
API series at all — confirmed by inspecting every route above; only the total export
volume is tracked. Documented here and surfaced as a caption on the page rather than
approximated or faked, per the spec's own "treat feedgas as out of scope" note and the
Definition of Done's "no fake series" requirement.

**Idempotency**: both `pull_gas_storage.py` (Session A) and `pull_production_exports.py`
are cheap full-history re-pulls (869 and 353 rows/series respectively — nowhere near
ENTSO-E/EirGrid's scale), so unlike those pipelines' Session-D-style trailing-window daily
entrypoints, no separate "narrow window" script is needed here. Both already serve
directly as the "weekly [storage]/monthly [production+exports] entrypoint" Spec 13 will
schedule (storage Thursdays per root `CLAUDE.md`'s release calendar; production/exports
whenever EIA's monthly report lands) — `write_ts_long`'s revision-based de-dup makes a
full re-pull naturally idempotent. Verified live: ran both scripts twice in a row, row
counts identical both times (353 production / 353 LNG exports / 6,952 storage rows).

Page section: a production-vs-LNG-exports dual-axis chart (`core.theme.dual_axis_chart`,
navy production / light-blue exports — the same primitive already used elsewhere, no new
chart type needed), with the feedgas caveat as an `st.caption`.
