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
(confirmed against that route's own metadata in `pipelines/futures/CLAUDE.md`). Two
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

**Correction to the claim above, since fixed: `pull_prices_weekly.py` did NOT actually
match `pull_weekly.py`'s precedent — found live, Task 5, 2026-09-06, and closed the same
day.** Every sibling weekly entrypoint (`pipelines/adanos/pull_weekly.py`,
`pipelines/cftc/pull_weekly.py`, `pipelines/macro/pull_weekly.py`,
`pipelines/social/pull_weekly.py`) ends with `if __name__ == "__main__": main()`.
`pipelines/eia/pull_prices_weekly.py` had no such guard — it only defined
`main = main_weekly` and `__all__`. Running `.venv/Scripts/python.exe -m
pipelines.eia.pull_prices_weekly` therefore did **nothing**: exit 0, no output, no rows
pulled, because nothing ever called `main()` — a silent success on a run that had actually
pulled nothing, the exact failure class this project has been hardening against. It still
worked correctly through `infra/run_scheduled.py` (which imports the module and calls
`module.main()` explicitly, never relying on a `__main__` block), so the scheduled cadence
was never affected — but the module could not be run standalone the way its own docstring
and every sibling file implied.

**Fixed**: added the same `if __name__ == "__main__": main()` guard every sibling carries.
Re-verified live immediately after: `.venv/Scripts/python.exe -m
pipelines.eia.pull_prices_weekly` now prints `eia prices petroleum/pri/gnd: 20628 rows` /
`wrote 20628 weekly EIA price rows` and exits 0 — the identical row count as calling
`pull_prices_weekly.main()` directly (which is what `run_scheduled.py` itself already
does), confirming the fix closes the gap without changing the scheduled path's behaviour.

## Task 5 — real pull outcomes, revision behaviour, and full-suite verification

First genuine runs of both entrypoints, 2026-09-06 (not cassette-derived; live against the
real EIA API, writing to the real lake):

`.venv/Scripts/python.exe -m pipelines.eia.pull_prices` (monthly, `MONTHLY_GROUPS`) — exit
0, no failures:
- `petroleum/pri/rac2` (RAC): 3,243 rows
- `petroleum/pri/land3` (LANDED_COST): 3,503 rows
- `natural-gas/pri/sum` (GAS): 1,878 rows
- `electricity/electric-power-operational-data` (GENERATOR_FUEL, both `cost-per-btu` and
  `consumption-for-eg` across 10 locations): 5,719 rows
- Total written: 14,343 rows, all at `monthly` frequency.

`.venv/Scripts/python.exe -m pipelines.eia.pull_prices_weekly` initially produced no
output and pulled nothing, for the reason recorded just above (missing `__main__` guard,
since fixed) — this was not a route failure. Calling `pull_prices_weekly.main()` directly
(equivalent to what `infra/run_scheduled.py` actually does in production) ran cleanly at
the time: exit 0, no failures, `petroleum/pri/gnd` (RETAIL): 20,628 rows at `weekly`
frequency. After the `__main__` guard fix, re-running `.venv/Scripts/python.exe -m
pipelines.eia.pull_prices_weekly` produced the identical result directly, with no
workaround needed: `eia prices petroleum/pri/gnd: 20628 rows` / `wrote 20628 weekly EIA
price rows`, exit 0.

**Revision behaviour, observed on the real lake, not just the isolated unit test below.**
The monthly pull was run twice in immediate succession. Both runs logged identical
per-route counts (3,243 / 3,503 / 1,878 / 5,719). Querying the lake directly after both
runs (`SELECT COUNT(*) ... WHERE series_id IN (RAC + LANDED_COST + GAS)`) returned exactly
8,624 rows — 3,243 + 3,503 + 1,878, i.e. the output of *one* pull, not two — and the
`ELEC.*`-prefixed generator-fuel series_ids returned exactly 5,719. `write_ts_long`'s
`(series_id, ts)` dedup, sorted by `revision_date`, replaced the first run's rows with the
second run's rather than accumulating a second copy, confirmed against real data.

A new unit test, `tests/test_eia_prices.py::test_a_revised_value_replaces_its_predecessor`,
covers the same behaviour in isolation (a synthetic PMM-style value revised across two
`write_ts_long` calls, monkeypatching `storage.LAKE_ROOT` to a `tmp_path` — never the real
lake): it asserts `read_ts_long` returns exactly one row carrying the later value. Verified
by hand that this test fails (`len(got) == 2`) if `write_ts_long`'s dedup is bypassed and
the second write's row is merely appended to the first's file — the assertion has real
teeth against a regression to append-only writes.

Full suite (`.venv/Scripts/pytest.exe`), lint and types, all run 2026-09-06 after the pulls
above: **723 passed, 16 deselected, 0 failed** (109s); `ruff check .` — all checks passed;
`mypy core pipelines infra` — no issues found in 157 source files.

## Spec 31 routes — confirmed live 2026-09-06

Task 0 (discovery only, no pull code) for Spec 31's six independent coverage items. This
plan builds items 1 and 3 (`natural-gas/stor/cap`, `natural-gas/cons/sum`); the other four
items' routes (plans 31B/31C) are walked here too, for series-facet shape only, since
discovery is cheap and shared and de-risks those plans before they are written.

| Route | Series facet? | Count | Codes used | Frequency | geo quirk | Item |
|---|---|---|---|---|---|---|
| `natural-gas/stor/cap` | yes | 123 | `NGM_EPG0_SACW0_R48_MMCF` (L48), `NGM_EPG0_SACW0_R83_MMCF` (East), `NGM_EPG0_SACW0_R85_MMCF` (Midwest), `NGM_EPG0_SACW0_R84_MMCF` (South Central, aggregate only), `NGM_EPG0_SACW0_R86_MMCF` (Mountain), `NGM_EPG0_SACW0_R91_MMCF` (Pacific) — all "Working" capacity | `monthly` | **yes** — `area-name` is the literal string `"NA"` for every row on this convention | 1 (31A) |
| `natural-gas/cons/sum` | yes | 315 | `N3010US2` (residential), `N3020US2` (commercial), `N3035US2` (industrial), `N3045US2` (electric power) — all US national | `monthly` | no — `geo` resolves to `"US"` cleanly | 3 (31A) |
| `electricity/rto/region-data` | **no** — 400 on `facet/series` | n/a | not selected — plan 31B scope; facets are `respondent`+`type`, one `value` data key | `hourly`/`local-hourly` only (declared) | not checked (no series id to key a `geo_map` on) | 2 (31B) |
| `electricity/rto/fuel-type-data` | **no** — 400 | n/a | not selected — plan 31B scope; facets `respondent`+`fueltype`, one `value` data key | `hourly`/`local-hourly` only (declared) | not checked | 2 (31B) |
| `electricity/rto/interchange-data` | **no** — 400 | n/a | not selected — plan 31B scope; facets `fromba`+`toba` (this is the `flows`-shaped one), one `value` data key | `hourly`/`local-hourly` only (declared) | not checked | 2 (31B) |
| `coal/consumption-and-quality` | **no** — 400 | n/a | not selected — plan 31C scope; facets `location`+`sector`; data keys `receipts`, `consumption`, `stocks`, `price`, `heat-content`, `sulfur-content`, `ash-content` | `quarterly`/`annual` only (declared) | not checked | 4 (31C) |
| `petroleum/pnp/capbio` | yes | 3 | not selected — plan 31C scope; all 3 are US national (biodiesel, renewable-diesel-and-other-biofuels, fuel-ethanol capacity) | `monthly` (declared and confirmed live) | no — sample code confirmed `geo="US"` | 5 (31C) |
| `petroleum/pnp/feedbiofuel` | yes | 26 | not selected — plan 31C scope; all 26 are US national feedstock inputs | `monthly` (declared and confirmed live) | no — sample code confirmed `geo="US"` | 5 (31C) |
| `petroleum/pnp/wprode` | yes | 6 | not selected — plan 31C scope; US + **all five** PADDs (1–5 all present — see correction below) | `weekly`/`four-week-average` (declared); `weekly` confirmed live | no — sample code confirmed `geo="US"` | 6 (31C) |

**Routes with no series facet (need a facet-dict query shape, not `facets[series][]`):**
`electricity/rto/region-data`, `electricity/rto/fuel-type-data`, `electricity/rto/interchange-data`,
`coal/consumption-and-quality`.
**Routes that failed or returned nothing:** none. Every route above returned either a real
series list or a real (non-series) facet/data-key shape when queried the right way — the
four "no series facet" routes return `400 Bad Request` specifically on `facet/series`,
exactly like `electricity/electric-power-operational-data` in Spec 30: a route shape, not a
failure.

**The `electricity/rto/*` routes are not one shape — confirmed live, not assumed, and none
of the three matches `get_operational_series`'s existing signature.** All three return `400
Bad Request` on `facet/series`, but they are three *different* non-series shapes:
- `region-data`: facets `respondent` (balancing-authority code, e.g. `PJM`, `ERCO`) and
  `type` (a demand/generation/forecast type code); one `data[0]=value`.
- `fuel-type-data`: facets `respondent` and `fueltype`; one `data[0]=value`.
- `interchange-data`: facets `fromba` and `toba` only — no `type`/`fueltype` at all, and
  this is the one that maps onto `get_flows`'s `(from_node, to_node)` shape, as the spec
  expects.
None matches `get_operational_series`'s `{fueltypeid, sectorid, location}` signature, so
plan 31B needs either a new method per shape or a more general facet-dict version of
`_fetch_operational_rows` — not decided here, `pipelines/eia/client.py` is out of scope for
Task 0.

**Grid Monitor is hourly-only, not monthly — a real volume finding for plan 31B.**
`region-data`, `fuel-type-data` and `interchange-data` each declare only `hourly` and
`local-hourly` frequencies (confirmed live via each route's own metadata endpoint,
`GET /v2/{route}` with no `/data`/`/facet` suffix) — there is no daily/monthly rollup to
fall back to. Combined with "all 65 Lower-48 balancing authorities" (the spec's own scope),
a full pull is hourly × 65 BAs × (demand + generation-by-fuel + interchange) — several
orders of magnitude more rows than any other route in this file. Plan 31B should decide its
own row-volume strategy (a trailing window, a BA subset, or a downsample) before writing
pull code; not decided here.

**`natural-gas/stor/cap` has a genuine convention split by era, and the spec's own
"1989–2026" claim does not hold at the regional level Task 1 needs — confirmed live, not
assumed.** The route carries two generations of series:
- An older, ambiguous-total convention (`N5290US2`, "U.S. Total Natural Gas Underground
  Storage Capacity") that does reach back to 1989-01 nationally and resolves `area-name` to
  `"US"` cleanly — but it is not explicitly split working/total, and its 2026-06 value
  (9,369,932 MMcf) is almost exactly double the "Working" L48 figure below, consistent with
  Total = Working + base gas, not the working-gas figure a fullness ratio needs.
- A newer, explicitly `Working`-labelled convention (`NGA_EPG0_SACW0_*`/`NGM_EPG0_SACW0_*`),
  the one chosen for the six codes above — but **every one of these regional series, old-
  style aggregates and new-style alike, starts 2013-01, not 1989.** Confirmed live: all six
  chosen codes return exactly 162 monthly rows each, 2013-01-01 to 2026-06-01. State-level
  codes (e.g. `N5290CA2`, California) reach back further (2002-01) and resolve `area-name`
  cleanly, but state-level is out of this plan's scope (national/region only, per the spec).

**Task 1 should present the capacity panel as 2013-onward, not 1989-onward** — the earlier
span exists only for the ambiguous national total, not for the working-gas regional
breakdown the fullness ratio is built on.

**`natural-gas/stor/cap`'s `area-name` quirk is not confined to the six chosen region-level
codes — confirmed live.** Every non-state-level series checked (both the new
`NGA_EPG0_SACW0_NUS_MMCF`/`NGM_EPG0_SACW0_R48_MMCF` national/regional codes and the old-
convention regional aggregates like `N5290832`) returns `area-name: "NA"` literally, for
every row — the same quirk as `natural-gas/stor/wkly` and `petroleum/pri/land3`. Only
genuinely state-level codes (e.g. `N5290CA2` → `"CALIFORNIA"`) and the one old-convention
*national* total (`N5290US2` → `"U.S."`) populate `area-name` properly. An explicit
`geo_map` (same pattern as `pull_gas_storage.py`'s `STORAGE_GEO_MAP`) is required for the
six codes chosen above; `_normalise_geo(area-name)` alone would collapse all six to
`geo="NA"`.

**Storage/capacity region pairing, against `pull_gas_storage.py`'s `STORAGE_GEO_MAP` —
confirmed live.** `natural-gas/stor/cap` (123 series, full facet dump inspected) has a
working-capacity series for six of `STORAGE_GEO_MAP`'s eight regions:

| `STORAGE_GEO_MAP` region | Capacity series? | Code |
|---|---|---|
| L48 | yes | `NGM_EPG0_SACW0_R48_MMCF` |
| East | yes | `NGM_EPG0_SACW0_R83_MMCF` |
| Midwest | yes | `NGM_EPG0_SACW0_R85_MMCF` |
| SouthCentral | yes (aggregate only) | `NGM_EPG0_SACW0_R84_MMCF` |
| SouthCentral_Salt | **no** | — |
| SouthCentral_Nonsalt | **no** | — |
| Mountain | yes | `NGM_EPG0_SACW0_R86_MMCF` |
| Pacific | yes | `NGM_EPG0_SACW0_R91_MMCF` |

**No salt/nonsalt capacity split exists — confirmed by inspecting the full 123-series facet
dump for this route: no series name or id contains "salt" or "non-salt" anywhere.**
`pull_gas_storage.py`'s two salt/nonsalt storage series (`NW2_EPG0_SSO_R33_BCF`,
`NW2_EPG0_SNO_R33_BCF`) will have to display without a percent-full figure of their own, or
fall back to the South Central *aggregate* capacity as a coarser denominator — a real gap,
not an oversight to fix here.

**`natural-gas/cons/sum` national codes — clean, confirmed live, no quirks.** `N3010US2`
(residential, 642 rows, 1973-01–2026-06), `N3020US2` (commercial, 642 rows, same span),
`N3035US2` (industrial, 306 rows, 2001-01–2026-06) and `N3045US2` (electric power, 306
rows, same span) all resolve `geo="US"` cleanly via the existing `_normalise_geo` path — no
`geo_map` needed for this route. No null `value` rows encountered across any of the four
(no drop message printed on the pull). Other national codes exist on this route but are out
of this plan's four-sector scope: `N9140US2` (total consumption, useful as a cross-check),
`N3025US2` (vehicle fuel), `N9160US2` (lease/plant fuel), `N9170US2` (pipeline &
distribution use), `N3060US2` (total delivered to consumers).

**`petroleum/pnp/wprode` carries all five PADDs, not "PADD1–4" as the spec text states —
confirmed live, not assumed; a spec correction for plan 31C.** All 6 series
(`W_EPOOXE_YOP_NUS_MBBLD` plus `_R10_`…`_R50_` for PADD1–5) were returned by
`list_series()`; PADD5 (`W_EPOOXE_YOP_R50_MBBLD`, West Coast) is real and present, not
missing. `weekly` frequency confirmed live on the US code (848 rows, 2010-06-04–2026-08-28);
the route also declares a `four-week-average` frequency (no `monthly`/`daily`/`annual`).
`geo` resolves to `"US"` cleanly on the sample checked.

**`petroleum/pnp/capbio` and `petroleum/pnp/feedbiofuel` — both clean, national-only, no
quirks, confirmed live.** `capbio` (3 series, all US-national capacity for
biodiesel/renewable-diesel-and-other/fuel-ethanol) and `feedbiofuel` (26 series, all
US-national feedstock inputs) both declare `monthly` only; sample codes from each
(`M_EPOOXE_8BDPC_NUS_MMGL`, `M_EPOOBDSO_YIFBP_NUS_MMLB`) confirmed live with `geo="US"` and
no nulls (66 and 68 rows respectively).

## Task 1 (31A) — gas storage capacity, and a real unit mismatch with the storage volumes it denominates

`pipelines/eia/pull_gas_capacity.py` pulls `natural-gas/stor/cap` (`monthly`) for the six
codes Task 0 confirmed live above (L48/East/Midwest/SouthCentral aggregate/Mountain/
Pacific), via `CAPACITY_GEO_MAP` and `EIAClient.get_series`'s `geo_map` parameter — required,
not optional, since `area-name` is the literal string `"NA"` for every row on this route
(same quirk as `natural-gas/stor/wkly`). Confirmed live 2026-09-06: 972 rows (162 per
series × 6), 2013-01 to 2026-06, unit `MMCF` on every row, no nulls.

**`SouthCentral_Salt` and `SouthCentral_Nonsalt` are deliberately absent from
`CAPACITY_GEO_MAP`** — Task 0 confirmed no salt/non-salt split exists anywhere in this
route's full 123-series facet dump (no series name or id contains "salt" or "non-salt").
Six capacity regions against `STORAGE_GEO_MAP`'s eight storage regions is therefore correct
coverage, not an omission — those two storage series have no capacity denominator of their
own and will need to fall back to the South Central aggregate capacity (a coarser
denominator) or display without a percent-full figure; not decided here.

**Real unit mismatch, confirmed live — capacity is `MMCF`, storage volumes are `BCF`.**
`pull_gas_storage.py`'s weekly series (`NW2_EPG0_SWO_*_BCF`) are billion cubic feet;
`pull_gas_capacity.py`'s monthly series (`NGM_EPG0_SACW0_*_MMCF`) are million cubic feet —
1 Bcf = 1,000 MMcf. Per this project's ingest-time convention (and this plan's own binding
constraint), **both are stored exactly as EIA publishes them, unconverted** — `pull_capacity`
does no unit reconciliation. Whatever computes the fullness ratio (storage ÷ capacity) must
convert one side by ×1,000 first, or it will read as ~0.1% full instead of ~100% full. Flagged
here for Task 3, which reads both series to build that ratio.

## Task 4 (31A) — final verification gate, real pulls, and a computed fullness ratio

Real (not cassette) runs, 2026-09-06:

`.venv/Scripts/python.exe -m pipelines.eia.pull_gas_capacity` — exit 0: `wrote 972 gas
capacity rows across 6 regions` (matches Task 1's live-confirmed count exactly).

`.venv/Scripts/python.exe -m pipelines.eia.pull_gas_consumption` — exit 0: `wrote 1896
gas consumption rows` (Task 0 counted 642+642+306+306 = 1,896 raw rows across the four
national sectors with no nulls — matches exactly).

**Region pairing, read from the real lake with `source="eia"`-narrowed `read_ts_long`
calls (never unbounded).** All 6 `CAPACITY_GEO_MAP` regions have a storage counterpart
and vice versa: L48/East/Midwest/SouthCentral/Mountain/Pacific each show 162 capacity
rows and 870 storage rows. The two `STORAGE_GEO_MAP` regions with no capacity series —
`SouthCentral_Salt` and `SouthCentral_Nonsalt` (870 storage rows each) — are exactly the
two Task 0 already named as expected gaps (no salt/non-salt capacity split exists on this
route). No unexpected mismatch either direction.

**Fullness ratio, computed for real with the MMcf→Bcf conversion (÷1,000) Task 1 flagged
as still outstanding — the actual point of this plan.** Latest capacity is monthly
(2026-06-01); latest storage is weekly (2026-08-28) — the ~3-month lag is EIA's own
publication cadence for `stor/cap`, not a bug, and capacity moves little month to month so
comparing latest-to-latest is a reasonable approximation:

| Region | Capacity (MMcf, 2026-06-01) | Capacity (Bcf, 2026-06-01) | Storage (Bcf, 2026-08-28) | Fullness |
|---|---|---|---|---|
| L48 | 4,748,719 | 4,748.7 | 3,214 | **67.7%** |
| East | 1,077,656 | 1,077.7 | 753 | **69.9%** |
| Midwest | 1,228,327 | 1,228.3 | 890 | **72.5%** |
| SouthCentral | 1,586,383 | 1,586.4 | 1,051 | **66.3%** |
| Mountain | 485,916 | 485.9 | 236 | **48.6%** |
| Pacific | 370,438 | 370.4 | 285 | **76.9%** |

(The five sub-L48 regions' storage sums to 3,215 against L48's stated 3,214 — EIA rounding, immaterial.)

**Believable.** All six land in a plausible band for late-August/early-September
injection-season fill (L48's 4,748.7 Bcf working capacity and 3,214 Bcf in storage are
both independently consistent with EIA's own published national figures for this period).
Mountain's lower fill (48.6%) is a real regional pattern, not a data error. None of this
is close to the ~0.07% a forgotten unit conversion would have produced — confirming the
conversion is the one thing that had to be right, and is.

**Full suite** (`.venv/Scripts/pytest.exe`, run after both real pulls above): 737 passed,
2 failed, 16 deselected (142s). Both failures —
`tests/test_pages_smoke.py::test_page_loads_without_raising[04_eu_power.py]` and
`[20_cracks.py]` — raised `MemoryError: cannot allocate memory for array` inside
`core/storage.py`'s DuckDB read, not inside any file this plan touched. Re-run in
isolation immediately after (`pytest tests/test_pages_smoke.py::...[04_eu_power.py]
...[20_cracks.py]`): **both passed**, 2/2, no error. Attributed to transient memory
pressure during the full-suite run (a concurrent session is active in this repo) rather
than a real regression — not fixed here per this task's verify-only scope.

**Lint**: `.venv/Scripts/ruff.exe check .` — all checks passed.

**Types**: `.venv/Scripts/mypy.exe core pipelines infra` — first invocation hit mypy's own
`INTERNAL ERROR` (a mypy-side crash, not a type error, most plausibly transient
file-contention with the same concurrent session). Immediately re-run with
`--show-traceback`: `Success: no issues found in 159 source files`.

**Two spec corrections made to `specs/31_eia-coverage-extensions.md`**, both contradicted
by Task 0's live discovery: item 1's "State and region level, 1989–2026" corrected to note
the regional series Task 1 actually uses begin 2013 (only an ambiguous national "Total"
series reaches 1989); item 6's "National and PADD1–4" corrected to "all five PADDs" (6
series: US plus PADD1 through PADD5, confirmed live by Task 0).

**Item 1 status, precisely: capacity data and the fullness ratio are real and in the
lake; the page section (Task 3) is not shipped.** It is blocked on a concurrent session's
permission for `apps/dashboard/**`, out of this task's scope, and not touched here.

## Task 3 (31A) — deferred page-section spec, recorded so it survives

Task 3 is blocked and may sit deferred for a while; the spec for it previously lived only
in a git-ignored ledger, which vanishes. Recorded here instead, per the plan
(`docs/superpowers/plans/2026-09-06-eia-31a-gas-completeness.md`, Task 3):

- Compute the ratio via `pipelines/eia/pull_gas_capacity.py::fullness_pct(storage_bcf,
  capacity_mmcf)`, never inline — it carries the ÷1,000 MMcf→Bcf conversion so no page has
  to remember it. Dividing Bcf by MMcf directly renders ~0.07% where the truth is ~70%.
- M-1/Y-1 rows must join the capacity row **in force at that as-of month** (a second
  `nearest_value_at_offset` call against the capacity series), not `iloc[-1]` — capacity
  is revised and grows, so reusing today's figure silently understates historical
  fullness.
- `SouthCentral_Salt` and `SouthCentral_Nonsalt` have no capacity denominator (see Task 1
  above) — the section must show its "no pair" message for these two and must not error
  or fall back to a guessed figure.
- Tests must assert the invariant (`0 < pct < 100`, L48 within a wide band) and must never
  bake in a measured percentage as an exact expected value — fill drifts with the
  injection season, so a hard-coded figure fails for the right reason at the wrong time.

## Spec 31B — Grid Monitor facet values, confirmed live 2026-09-07

Task 0 (discovery only, no pull code — Tasks 1–5 build the client method and pull scripts).
Live queries against all three `electricity/rto/*` routes' `facet/<name>` endpoints (not
`facet/series`, which 400s on all three, per plan 31A). The brief's own throwaway-script
import line (`from core.config import settings`) does not exist in this repo — the real
module is `core.settings` (confirmed: `pipelines/eia/client.py` already imports it that
way); used `core.settings` for every script below, no other deviation.

| Route | Facet | Values used | Total available |
|---|---|---|---|
| electricity/rto/region-data | respondent | `ERCO`, `PJM`, `MISO`, `SWPP`, `CISO`, `NYIS`, `ISNE`, `US48` — all 8 confirmed present | 83 |
| electricity/rto/region-data | type | `D` (Demand), `DF` (Day-ahead demand forecast), `NG` (Net generation), `TI` (Total interchange) — all 4 declared codes used, matching the brief's expected demand/forecast/generation/interchange set exactly | 4 |
| electricity/rto/fuel-type-data | fueltype | `NG` (Natural Gas) — the one gas-burning fuel type this plan needs; present and unique (not one of the duplicated ids, see below) | 20 raw facet rows / **16 unique codes** (4 ids listed twice — see finding below) |
| electricity/rto/interchange-data | fromba/toba pairs | 10 directed pairs among the 8 chosen respondents (5 undirected corridors): `ERCO`↔`SWPP`, `ISNE`↔`NYIS`, `MISO`↔`PJM`, `MISO`↔`SWPP`, `NYIS`↔`PJM` | fromba: 83, toba: 92 |

**Row field names on a real hourly response (region-data, `respondent=ERCO`, `type=D`):**
`period`, `respondent`, `respondent-name`, `type`, `type-name`, `value`, `value-units`.
**Value column:** `value`  **Unit column:** `value-units`  **Unit string:** `megawatthours`
(confirmed on all three routes — `get_operational_series`'s "value column named after the
data key, units column is `<key>-units`" pattern holds exactly here, where the key is
literally `value`, giving `value`/`value-units` rather than a bare `units`).
**Period format:** `2026-09-01T00` (`YYYY-MM-DDTHH`), confirmed.
**start/end accepted as:** `YYYY-MM-DDTHH`, **inclusive on both ends** and genuinely
narrowing — confirmed live with a 3-hour window (`start=2026-09-01T20`,
`end=2026-09-01T22`) returning exactly 3 rows (`T20`, `T21`, `T22`). A consequence worth
flagging for Task 6's backfill arithmetic: a "one calendar day" window expressed as
`start=<day>T00`/`end=<day+1>T00` returns **25** hourly points, not 24, because both
endpoints are inclusive — this is exactly why Step 3's 8-respondent/4-type count below is
800, not 768.
**Rows for one day x 8 respondents (region-data):** **800** (8 respondents × 4 types × 25
inclusive hourly periods — `total` in the response matches exactly, confirmed live
2026-09-07). Well under the 5,000-row page size — **no paging needed for one day at this
scope**. Scaled to a 90-day backfill: 800 × 90 = 72,000 rows for `region-data` alone across
the 8 respondents, i.e. 15 requests at `length=5000` (72,000 ÷ 5,000) — Task 6's backfill
guidance should use this real number, not re-derive it.
**Real interchange pairs among the chosen BAs:** only **5 undirected corridors** connect
the 8 chosen BAs to each other (10 directed rows, both ends in the target set): `ERCO↔SWPP`,
`ISNE↔NYIS`, `MISO↔PJM`, `MISO↔SWPP`, `NYIS↔PJM`. **`ERCO` and `PJM` — the two respondents
Spec 31 item 2 exists specifically to reach — are not directly interconnected**; ERCO's only
real corridors are `SWPP` and `CEN` (Mexico's Comisión Federal de Electricidad control
area), and PJM's are `CPLE`, `CPLW`, `DUK`, `LGEE`, `MISO`, `NYIS`, `TVA`. This is not an
empty-corridor failure (ERCO does have real interchange data, non-zero, confirmed:
`ERCO→SWPP` values ranged -460 to 135 MWh over the sample hour), just a real topology fact
Task 5 needs to know before assuming every pair of the 8 chosen BAs has its own series.
`US48` (the Lower-48 aggregate) never appears as a `toba` value at all — confirmed missing
from the full 92-value `toba` facet dump — but does appear as a `fromba`, exporting only to
`CAN` and `MEX` (the two cross-border aggregate corridors), which is the expected shape for
a whole-footprint aggregate rather than a real gap.
**Respondent ids requested but NOT found:** none — all 8 (`ERCO`, `PJM`, `MISO`, `SWPP`,
`CISO`, `NYIS`, `ISNE`, `US48`) are present under every facet checked (`region-data`
respondent, `fuel-type-data` respondent, `interchange-data` fromba), **except** `US48`
under `interchange-data`'s `toba` facet specifically (see finding above — expected given
`US48`'s aggregate role, not a missing respondent).

**Real finding: `fuel-type-data`'s `fueltype` facet carries 4 duplicate ids with differing
display names — confirmed live, not a parsing bug.** `PS` ("Pumped Storage" / "Pumped
storage"), `UES` ("Unknown Energy" / "Unknown energy storage"), `BAT` ("Battery" /
"Battery storage"), `SNB` ("Solar Battery" / "Solar with integrated battery storage") each
appear twice with the same id and a different name string — 20 raw rows resolve to 16
unique ids. Consistent with an EIA-side naming-convention update where the old display
string was never retired from the facet listing. Does not affect this plan: `NG` (the only
code needed) appears exactly once, name `"Natural Gas"`, no duplicate.

**Real finding: the descriptive name field for `fueltype` is `type-name`, not
`fueltype-name`.** Confirmed on the `fuel-type-data` response row: the code field is
`fueltype` (e.g. `"NG"`) but its paired human-readable field is named `type-name` (e.g.
`"Natural Gas"`) — the same field name `region-data` uses for its own, semantically
different `type` code. A field-name lookup keyed naively off the facet name (`fueltype` →
`fueltype-name`) would silently return `KeyError` or `None`; Tasks 3/4 must read `type-name`
for this route's fuel description, not a derived `f"{facet}-name"` string.

**Confirmed clean, no surprises:** `respondent`/`type`/`fueltype`/`fromba`/`toba` all come
back on every row of their respective route (never missing) alongside a matching
`<field>-name` descriptive column; region-data's 4 `type` codes exactly match the brief's
expected demand/forecast/generation/interchange set with no fifth or missing code;
`fuel-type-data`'s rows carry both `respondent`/`respondent-name` and `fueltype`/`type-name`
together, confirming the minted series-id scheme Tasks 3/4 will need can key off
`respondent`+`fueltype` per row without a second lookup.

## Task 6 (31B) — scheduled, backfilled for real, and the final gate

`infra/run_scheduled.py`'s `daily` group now calls all three pulls (`eia_rto_demand` →
`pipelines.eia.pull_rto_demand`, `eia_rto_fuel_mix` → `pipelines.eia.pull_rto_fuel_mix`,
`eia_rto_interchange` → `pipelines.eia.pull_rto_interchange`), appended after
`derived_curve` — no ordering dependency among them or on anything earlier in the group.
`git status` was clean immediately before this edit (no concurrent-session conflict);
`tests/test_run_scheduled.py` passes (7/7) with the three new entries present.

**Real 90-day backfill, run live against the EIA API, 2026-09-08 — not cassette-derived:**

| Pull | Command | Rows written | Wall time |
|---|---|---|---|
| `pull_rto_demand` | `--days 90` | 68,075 (8 balancing authorities) | ~36s |
| `pull_rto_fuel_mix` | `--days 90` | 118,072 (8 balancing authorities) | ~74s |
| `pull_rto_interchange` | `--days 90` | 90,066 (45 corridors) | ~44s |

All three exited 0, no `PartialFailureError`. Task 0's own baseline was 800 rows/day ×
90 = 72,000 rows for `region-data` alone; the real `pull_rto_demand` count (68,075) lands
under that estimate (some hours are dropped by EIA's own short reporting lag at the
trailing edge of the window, not a pull defect), and neither `pull_rto_fuel_mix` nor
`pull_rto_interchange` — which were never part of that specific estimate — came anywhere
close to a volume or timing concern (each finished in well under a minute, not "a few
minutes"). Decision A's proportionality goal holds in practice, not just in projection.

**BA coverage actually ingested: 8 of EIA's 65 Lower-48 balancing authorities** —
`ERCO`, `PJM`, `MISO`, `SWPP`, `CISO`, `NYIS`, `ISNE`, `US48` (`pipelines/eia/rto.py`'s
`RTO_RESPONDENTS`). This is deliberate, not partial coverage awaiting a later widening:
hourly data on these routes has no daily/monthly rollup, so all 65 BAs × 3 datasets would
be load-research-scale volume the spec explicitly rules out. The 8 chosen are the large
gas-burning markets `pipelines/gridstatus_iso/` cannot reach (ERCOT blocked by
Incapsula/Imperva bot protection, PJM needs a Data Miner 2 key this project doesn't hold)
plus the `US48` national aggregate.

**Minted series-id schemes — permanent once written to the lake:**
- `RTO.REGION.<respondent>.<type>.H` — e.g. `RTO.REGION.ERCO.D.H` (demand),
  `RTO.REGION.PJM.NG.H` (net generation).
- `RTO.FUEL.<respondent>.<fueltype>.H` — e.g. `RTO.FUEL.PJM.NG.H` (natural-gas-fired
  generation).
- **The `NG` collision, and how the REGION/FUEL segment prevents it:** `region-data`'s
  `type=NG` ("Net Generation") and `fuel-type-data`'s `fueltype=NG` ("Natural Gas") are
  the same two-letter code from two different facets on two different routes. Without a
  route-identifying segment in the id, `RTO.ERCO.NG.H` would be ambiguous between "ERCOT's
  total net generation" and "ERCOT's natural-gas-fired generation" — a fuel-mix value would
  silently overwrite a net-generation value in the lake (or vice versa) on whichever pull
  ran second. The literal `REGION`/`FUEL` segment (`region_series_id`/`fuel_series_id` in
  `pipelines/eia/rto.py`) keeps the two id spaces disjoint by construction. Confirmed live:
  after the backfill, `RTO.REGION.ERCO.NG.H` (8,471 region rows for ERCOT total, of which
  net-generation is one `type`) and `RTO.FUEL.ERCO.NG.H` (2,147 gas-fired rows) both exist
  as distinct, independently-readable series — no row from one was overwritten by the other.

**Step 3 — the data answers the question this item exists for.** Read live from the lake,
narrowed by `source="eia"` and `series_prefix=`/exact `series_ids=`, per the global
constraints:

| BA | Gas-fired rows (`RTO.FUEL.<ba>.NG.H`) | Region rows (`RTO.REGION.<ba>.*`) | Gas burn span | Unit |
|---|---|---|---|---|
| ERCO | 2,147 | 8,471 | 2026-06-10 18:00 → 2026-09-08 04:00 | megawatthours |
| PJM | 2,146 | 8,613 | 2026-06-10 18:00 → 2026-09-08 03:00 | megawatthours |

**Both non-empty, spanning the full backfill window.** This is the one outcome that would
have made the whole plan pointless had it come back empty — it didn't. `flows` interchange
rows: 90,066 across 45 corridors (`mode == "grid_interchange"`), matching the pull's own
reported count exactly.

**Real interchange corridor list (45, `(from_node, to_node)`, confirmed from the live
lake):** `CISO↔{AZPS, BANC, BPAT, CEN, IID, LDWP, NEVP, PACW, SRP, TIDC, WALC}`,
`ERCO↔{CEN, SWPP}`, `ISNE↔{HQT, NBSO, NYIS}`,
`MISO↔{AECI, IESO, LGEE, MHEB, PJM, SIKE, SOCO, SPA, SWPP, TVA}`,
`NYIS↔{HQT, IESO, ISNE, PJM}`, `PJM↔{CPLE, CPLW, DUK, LGEE, MISO, NYIS, TVA}`,
`SWPP↔{AECI, EPE, ERCO, MISO, PNM, PSCO}`, `US48↔{CAN, MEX}`. Each row names its own
counterparty in `toba`, so a corridor to a BA outside `RTO_RESPONDENTS` (e.g. `ERCO↔CEN`,
Mexico's CFE) is captured too — confirming Task 0's finding that ERCOT and PJM are not
directly interconnected (their only shared link is via `MISO`/`SWPP`), which is real grid
topology, not a gap.

**Step 4 — the double-count guard, proved live, not just by code inspection.** Total
`flows` row count for `source="eia"` before any re-run: **100,092**. `pull_rto_interchange
--days 3` was then run twice in immediate succession, each run logging `wrote 1381 RTO
interchange rows across 44 corridors (3d window)`. Total row count after the first re-run:
**100,092** (unchanged). Total row count after the second re-run: **100,092** (unchanged
again). A full 3-day window's worth of corridors would have added on the order of
thousands of rows had `replace_window` failed to delete-and-rewrite; instead the count held
exactly flat both times, because the 3-day window was already fully covered by the earlier
90-day backfill and `write_flows`'s `replace_window=(df["ts"].min(), df["ts"].max())` (the
Task 5 fix — derived from the pulled frame's own timestamps, not a second clock read)
deleted and rewrote the same rows rather than appending a second copy. **The guard holds
under a real, live re-run, not only in the unit test.**

**Step 5 — full gate, run after the real backfill above, 2026-09-08:** `pytest` — 759
passed, 16 deselected, 0 failed (113s). `ruff check .` initially found one unsorted-import
violation in `tests/test_eia_client_facets.py` (left over from Task 1's own commit, not a
concurrent session's file) — fixed and committed separately (`6f60ca0`); re-run clean.
`mypy core pipelines infra` — no issues found in 163 source files. No concurrent-session
test failures encountered in any file this plan didn't touch.
