# pipelines/eia — notes

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
schedule (storage Thursdays per root `NOTES.md`'s release calendar; production/exports
whenever EIA's monthly report lands) — `write_ts_long`'s revision-based de-dup makes a
full re-pull naturally idempotent. Verified live: ran both scripts twice in a row, row
counts identical both times (353 production / 353 LNG exports / 6,952 storage rows).

Page section: a production-vs-LNG-exports dual-axis chart (`core.theme.dual_axis_chart`,
navy production / light-blue exports — the same primitive already used elsewhere, no new
chart type needed), with the feedgas caveat as an `st.caption`.

## Spec 30 price routes — confirmed live 2026-09-06

Task 0 (discovery only, no pull code). All six of the spec's own candidate routes were
walked via `list_series()`/`facet/series` for real; two genuine surprises turned up that
change what Tasks 1 and 2 should build, recorded below rather than silently worked around.

| Route | Series discovered | Codes used | Frequency | Notes |
|---|---|---|---|---|
| `petroleum/pri/rac2` | 18 | `R0000____3`, `R1200____3`, `R1300____3` (US composite/domestic/imported); `R0010____3`, `R0020____3`, `R0030____3`, `R0040____3`, `R0050____3` (PADD1-5 composite) | `monthly` | 631 rows confirmed on `R0000____3`; no nulls. `weekly`/`daily` both raise `400 Bad Request` (loud failure, not silent-empty) — annual also works (58 rows). |
| `petroleum/pri/gnd` | 311 | Gasoline (All Grades, All Formulations): `EMM_EPM0_PTE_NUS_DPG`, `_R10_`, `_R20_`, `_R30_`, `_R40_`, `_R50_DPG` (US + PADD1-5); Diesel (No 2, unrestricted sulfur grade): `EMD_EPD2D_PTE_NUS_DPG`, `_R10_`, `_R20_`, `_R30_`, `_R40_`, `_R50_DPG` (US + PADD1-5) — 12 codes total | `weekly` | 1,744 rows confirmed on `EMM_EPM0_PTE_NUS_DPG`; no nulls. `daily` raises `400 Bad Request`; `monthly`/`annual` also declared and work. |
| `natural-gas/pri/sum` | 423 | `N3050US3` (US citygate), `N3010US3` (US residential), `N3020US3` (US commercial), `N3035US3` (US industrial) | `monthly` | See null-value finding below. `weekly` raises `400 Bad Request`. |
| `natural-gas/pri/rescom` | 20 | none used — see finding below | `monthly` | Confirmed live; declared frequencies `M`/`A` only. |
| `petroleum/pri/land3` | 7 | `I000000208`, `I000000258`, `I000000308`, `I000000358`, `I000000408`, `I000000458`, `I000000998` (all 7 gravity bands) | `monthly` | Not one of the spec's six candidate routes — found by walking `GET /v2/petroleum/pri` for real, same "walk the category tree" discipline as Session C's `natural-gas/sum/lsum` find. Answers the gravity-band question below. 522 rows confirmed on `I000000208` (1983-01 to 2026-06), no nulls. `area-name` is the literal string `"NA"` for every row (same quirk as `natural-gas/stor/wkly`) — a future pull needs a `geo_map`, not `_normalise_geo`. |
| `electricity/electric-power-operational-data` | not series-based — see finding below | `fueltypeid=NG` + `sectorid=98` + `location=<code>`, `data=cost-per-btu` and `data=consumption-for-eg`; locations confirmed with a real (non-null) latest value: `US`, `TX`, `CA`, `PA`, `LA`, `OH`, `NY`, `IL`, `NJ`, `MI` (10 codes) | `monthly` | `weekly`/`daily` both raise `400 Bad Request`; `quarterly`/`annual` also declared and work. |

**`electricity/electric-power-operational-data` has no `series` facet at all — confirmed
live, not an `EIAClient` bug.** `GET /v2/{route}/facet/series` returns `400 Bad Request` for
this route (`list_series()` therefore cannot be used on it). `GET /v2/{route}` (no
`/data`/`/facet` suffix) shows why: this route's own facets are `location`, `sectorid`,
`fueltypeid` — a genuinely different shape from every other route in this file, which all
key off a single `series` facet. A row is selected by combining `facets[fueltypeid][]=NG`,
`facets[sectorid][]=98` ("(98) Electric Power" — the electric-power-sector aggregate, not
"(1) Electric Utility" or any of the narrower IPP/CHP sector codes also on offer) and
`facets[location][]=<code>`, with `data[0]=cost-per-btu` (EPM Table 4.13, confirmed live:
`$3.175/MMBtu` for US, 2026-06, unit string `"dollars per million Btu"`) or
`data[0]=consumption-for-eg` (EPM Table 2.4, confirmed live: `1,171,229 thousand Mcf` for
US, 2026-06). **`EIAClient.get_series`/`list_series` as written cannot pull this route at
all** — Task 1/2 needs a new method (or a route-specific query builder) that takes
`{fueltypeid, sectorid, location}` facet filters and a `data[0]` column name, not a
`facets[series][]` list. Not fixed here — Task 0 touches no `pipelines/eia/*.py` file.

**`location` mixes real states with census-division aggregates under one facet — this is
what the spec's own "State-level, not census division" note is warning about.** Confirmed
live: alongside `US` and the 51 real state/DC/PR codes, the same `location` facet also
returns 11 aggregate codes (`NEW`, `MAT`, `ENC`, `SAT`, `ESC`, `WNC`, `MTN`, `WSC`, `PCC`,
`PCN`, `90`) that are census divisions, not states. There is no separate facet to exclude
them by — Task 1/2 must filter `location` to the real state codes explicitly. Several real
states return a row with `cost-per-btu: null` for the latest month rather than being absent
(`FL`, `NC`, `GA`, `AZ`, `CO`, `OK`, `WV`, `WA` all checked null for 2026-06; `TX`, `CA`,
`PA`, `LA`, `OH`, `NY`, `IL`, `NJ`, `MI` all checked non-null) — the 10 codes above were
chosen from the confirmed-non-null set, not guessed from population or news familiarity.

**Real, live-confirmed gap: `natural-gas/pri/sum` and `natural-gas/pri/rescom` return a
literal JSON `null` for `value` on a meaningful fraction of early-history rows, and
`EIAClient.get_series` crashes on it rather than returning an empty or partial result.**
`float(row["value"])` raises `TypeError: float() argument must be a string or a real
number, not 'NoneType'` the first time a full-history pull hits one of these rows — this is
not the "wrong frequency returns empty" trap the brief warned about, it is a **crash**, and
worse for being unencountered until a full-history (not tail) pull runs. Confirmed live by
counting: `N3050US3` (citygate) 129/642 null rows (1973-01–1983-09 mostly), `N3010US3`
(residential) 96/642, `N3020US3` (commercial) 129/642, `N3035US3` (industrial, starts
2001-01) 0/306 clean, and a `natural-gas/pri/rescom` sample (`N3010NY3`) 5/450. `rac2`,
`gnd` and `land3` samples checked clean (0 nulls) over their full history. **Task 1/2 must
drop or otherwise handle null `value` rows before/inside any full-history pull of
`natural-gas/pri/sum` or `pri/rescom`** — not fixed here, `pipelines/eia/client.py` is out
of scope for Task 0.

**`natural-gas/pri/rescom` carries no national-level series at all — confirmed live, not
assumed from the route's name.** All 20 series under this route are per-state residential
or commercial prices (e.g. `N3010NY3`, `N3020MD3`); there is no `US`-suffixed series and no
industrial series anywhere in this route. The "US citygate, residential, commercial and
industrial delivered price" the spec asks for all live under `natural-gas/pri/sum` instead
(`N3050US3`/`N3010US3`/`N3020US3`/`N3035US3` above) — `pri/sum` already carries the national
residential/commercial rollups `pri/rescom` was expected to supply, so `pri/rescom` is not
used by this family. (One EIA naming inconsistency hit while searching: the industrial
series is named `"United States Natural Gas Industrial Price"`, not `"U.S. ..."` like every
other national series in this route — a literal-string `"U.S."` search silently misses it;
re-run with `"United States"` included before concluding a national series doesn't exist.)

**`natural-gas/pri/fut` decision: not ingested, because it duplicates data this project
already owns under a different, incompatible convention.** The route carries exactly 5
series: `RNGWHHD` (Henry Hub spot) and `RNGC1`..`RNGC4` (futures contracts 1-4), confirmed
live, `$/MMBtu`, declared frequencies `D`/`W`/`M`/`A`, span 1993-12-24 to **2026-08-28 —
this route is current, unlike `petroleum/pri/fut` which stopped updating 2024-04-05**
(confirmed against that route's own metadata in `pipelines/futures/NOTES.md`). Two
independent reasons to leave it out of Spec 30:
1. `RNGWHHD` is the same real-world benchmark as `fred.dhhngsp`, already the lake's one and
   only gas-price series (Spec 30's own "why this exists" section names it) — ingesting it
   again under `source="eia"` would give the lake two Henry Hub spot series under two
   conventions with no stated reconciliation.
2. `RNGC1`..`RNGC4` are rank-labelled futures contracts — structurally identical to
   `petroleum/pri/fut`'s own `RCLC1`..`RCLC4` etc., which `pipelines/futures/eia_futures.py`
   already ingests into `fut.<root>.f01..f04.settle` (`source="eia"`) as part of **Spec
   18**, not Spec 30. Spec 18's `pipelines/futures/client.py` already treats `ng` as one of
   its 7 roots (currently with zero real rows, since no IBKR/manual/barchart source covers
   it yet).
   Pulling `RNGC1`..`RNGC4` a second time via Spec 30's `pull_prices.py` would write the
   same underlying instrument under a second, separately-maintained convention — exactly
   the "same futures twice under two conventions" risk the brief calls out by name. If live
   NG futures are wanted, the natural-gas analogue of `eia_futures.py` (adding an `ng` root
   there, using this now-discovered non-discontinued route) is Spec 18's job, not Spec 30's.

**Gravity-banded landed-cost series: exists, at `petroleum/pri/land3`.** Not one of the
spec's six candidate routes — found by walking `GET /v2/petroleum/pri`'s own route list
live rather than assuming the concept had no home. 7 series, one per API gravity band (see
table above), monthly, `$/BBL`, 1983-01–2026-06. This is the series Spec 30 Session C's
"Landed cost by API gravity band" chart needs; it is real and should not be dropped.
(`petroleum/pri/dfp3` — Domestic Crude Oil First Purchase Prices by API Gravity — and
`petroleum/pri/imc3` — FOB Costs of Imported Crude by API Gravity — exist alongside it with
the same 7-band shape, confirmed live but not chosen for this spec's scope.)

**Routes that returned nothing or failed:**
`electricity/electric-power-operational-data`'s `facet/series` call itself fails with `400
Bad Request` (no `series` facet on this route at all — see finding above; the route's
*data* endpoint works once queried with its real facet shape). Every other candidate route
returned real series. `natural-gas/pri/rescom` returned real series but none usable at the
national scope this family needs (see finding above) — a route that "worked" but
contributed zero codes, not a route that failed.

## Task 1 — a reviewer claim about `EMD_EPD2D_PTE_R50_DPG` checked and not upheld

A Task 1 review raised a finding that `EMD_EPD2D_PTE_R50_DPG` (PADD5/West Coast No. 2
diesel, one of `RETAIL`'s 12 codes in `pull_prices.py`) was effectively dead — "26 rows:
1994-04 through 1994-09, plus one isolated point at 2010-09-13. Nothing since" — and should
be dropped from `RETAIL`.

**Checked live and via the already-recorded cassette, and not upheld.** A fresh
`GET /v2/petroleum/pri/gnd/data/` for this exact series id (weekly, `sort=desc`,
`length=5000`), run 2026-09-06, returned 1,694 rows spanning 1994-03-21 to **2026-08-31**
(the same latest date as every other `RETAIL` code) with no gap in the period sequence
larger than 14 days — i.e. no missing weeks anywhere in 32 years of history, let alone a
16-year one. The cassette recorded for
`tests/cassettes/test_eia_prices/test_retail_prices_are_weekly_and_dollars_per_gallon.yaml`
shows the identical 1,694-row, 1994-03-21–2026-08-31 span for this series when loaded
through `pull_prices.pull_group`. All 12 `RETAIL` codes, re-checked individually, report
`total: 1744` (gasoline codes) or `total: 1694` (diesel codes) with `2026-08-31` as the
latest period — none show the pattern the finding described. `EMD_EPD2D_PTE_R50_DPG` was
**not** removed from `RETAIL`; it remains one of the 12 codes.

Recorded here rather than silently dropped, per this file's own discipline of writing down
findings a future session can check without re-walking the API — a later session hitting
either version of this claim (dead series, or "no it isn't") should not have to redo this
work from scratch.

## Task 2 — gas prices, and a minted series-ID scheme for the no-`series`-facet route

`natural-gas/pri/sum` (`pull_prices.GAS`) pulls clean via the existing `get_series` —
confirmed live, 2,232 raw rows across the 4 codes, 1,878 surviving the null-`value` skip
(129/129/96/0 dropped on `N3050US3`/`N3020US3`/`N3010US3`/`N3035US3`, matching Task 0's
counts above exactly), unit `$/MCF` on every surviving row.

**`electricity/electric-power-operational-data` (Task 0's no-`series`-facet finding
above) needed a genuinely new client method, not a workaround inside `get_series`.**
`EIAClient.get_operational_series(route, data_keys, fueltypeid, sectorid, location,
frequency)` selects rows by `{fueltypeid, sectorid, location}` facets instead of a
`series` list, fetching one `data_key` (e.g. `"cost-per-btu"`) at a time — each key
names both its own value column and a `<data_key>-units` column in the response, unlike
every other route's fixed `"value"`/`"units"` pair. `_fetch_operational_rows` is a
sibling to `_fetch_rows` with an identical offset/`PAGE_SIZE` paging loop, just a
different `params` shape.

**Series-ID scheme (minted, since EIA gives this route no id at all):**
`ELEC.<DATA_KEY_UPPER_SNAKE>.<fueltypeid>-<location>-<sectorid>.<freq_code>`, e.g.
`ELEC.COST_PER_BTU.NG-US-98.M` and `ELEC.COST_PER_BTU.NG-TX-98.M` — deterministic from
each row's own facets (uppercase the `data_key`, hyphens to underscores; `M` from
`_FREQUENCY_CODES` in `client.py`), following EIA's own native dotted-with-hyphens
convention (`ELEC.<short>.<fuel>-<geo>-<sector>.<freq>`), not the lowercase-dotted style
Specs 17–29 use for this lake's other series ids. `pull_prices.GENERATOR_FUEL =
["cost-per-btu", "consumption-for-eg"]` is the two `data_key`s requested, fixed to
`fueltypeid=NG` and `sectorid=98` ("Electric Power" aggregate). These ids are permanent
once written to the lake.

**State-level, not national-only — corrected after an initial national-only submission
was reviewed against the spec.** Spec 30's own chart (`specs/30_eia-price-coverage.md`
line 122, "State delivered gas cost to generators vs Henry Hub, with the spread
annotated") needs the *dispersion* across states; a single US average washes out
exactly what the chart exists to show. `pull_prices.GENERATOR_FUEL_LOCATIONS = ["US",
"TX", "CA", "PA", "LA", "OH", "NY", "IL", "NJ", "MI"]` — the same 10 codes Task 0
confirmed live (2026-09-06) carry a real, non-null `cost-per-btu` for the latest month
(`US` kept as the national benchmark line the state series are compared against).
`FL`, `NC`, `GA`, `AZ`, `CO`, `OK`, `WV`, `WA` were checked the same way and excluded —
each returned `cost-per-btu: null` for 2026-06 rather than a real value. `location`
mixes real states with census-division aggregates under one facet with no separating
facet, so this list cannot be extended by pattern; any new state needs the same
non-null check Task 0 did, not a guess.

`EIAClient._fetch_operational_rows`/`get_operational_series` take a `locations:
list[str]`, not a single code — confirmed live that `facets[location][]` accepts a
repeated value exactly like `facets[series][]` does elsewhere in this client, so all 10
locations are fetched in one paged request per `data_key` (2 requests total, each
row tagged with its own `location`), not one request per location. Confirmed live,
2026-09-06: `cost-per-btu`, 3,060 raw rows across the 10 locations (306 each), with
164/32/75/28/15/14/43/16/14 nulls dropped on LA/MI/IL/CA/NJ/NY/OH/PA/TX respectively
(0 on `US`) — all 10 locations still non-null for the latest month (2026-06) after
filtering, matching Task 0's finding exactly. `consumption-for-eg`: 3,060 raw rows, 0
nulls anywhere. Final pulled frame: 5,719 rows across both data keys and all 10
locations, e.g. `TX`: 598 rows, `LA`: 448 rows (fewest — most nulls dropped, still
correctly included since its *latest* value is real). Null rows are always skipped, per
`get_series`'s own established convention — never fabricated as zero.

The test covering this route (`tests/test_eia_prices.py::
test_generator_fuel_cost_returns_valid_ts_long`) asserts `set(df["geo"]) ==
set(GENERATOR_FUEL_LOCATIONS)` specifically because a regression back to national-only
would otherwise still pass every other assertion on that test.

`pipelines/eia/pull_prices_weekly.py` is a thin re-export of `pull_prices.main_weekly`
(the `petroleum/pri/gnd` retail-price pull, `WEEKLY_GROUPS`), matching
`pipelines/adanos/pull_weekly.py`'s precedent — so `infra/run_scheduled.py` can address
both EIA price cadences by the same `pull_<cadence>` convention as every other pipeline.
