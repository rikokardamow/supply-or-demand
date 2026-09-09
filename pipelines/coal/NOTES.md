# pipelines/coal — notes

## Route and facets

`coal/consumption-and-quality` (EIA API v2). **No `series` facet at all** — confirmed
live, `GET /v2/coal/consumption-and-quality/facet/series` returns `400 Bad Request` with
body `{"error": "Invalid facet 'series' provided. The only valid facets are 'location',
and 'sector'.", "code": 400}`. Rows are selected by `location` + `sector` facets instead,
via `EIAClient.get_facet_series` (plan 31B's shared facet-dict fetcher), and this package
mints its own series id from each row — see below.

Declared frequencies are `quarterly` and `annual` only — there is no monthly or weekly
coal data on this API at any route. This package uses `quarterly` (`_FREQ_SUFFIX = "Q"`).
Period format on a real row is `"YYYY-Qn"`, e.g. `"2026-Q2"`.

`location` carries 74 values, mixing 53 real geographies (50 states + DC + PR + `US`)
with 21 census-region aggregate codes. `US` is confirmed live as a real, non-null
location — this package only pulls `LOCATIONS = ["US"]`, so the aggregate-code mixing
problem doesn't affect it, but any future state-level pull must filter both the
numeric (`80`-`90`) and letter-mnemonic (`NEW`, `MAT`, `ENC`, ...) aggregate codes out
explicitly, the same discipline `pipelines/eia/pull_prices.py`'s
`GENERATOR_FUEL_LOCATIONS` already applies for a different route.

## Power-sector code

`POWER_SECTOR = "98"` ("Electric Power") — confirmed live from the route's 8-value
`sector` facet dump, and the same aggregate code EIA uses for
`electricity/electric-power-operational-data`'s `sectorid=98` elsewhere in this project.
**Not** `"1"` ("Electric Utility"), a narrower, different sector, nor `94`
("Independent Power Producers"), `2`/`3` ("IPP Non-CHP"/"IPP CHP"), `9` ("Coke Plants"),
`8` ("Commercial and Institutional") or `10` ("Other Industrial") — none of those is the
power-sector aggregate this item scopes to.

## Minted series-id scheme — permanent once written

`COAL.<DATA_KEY>.<location>-<sector>.Q`, e.g. `COAL.PRICE.US-98.Q` — deterministic from
each row's own `location`/`sector` facets, following `get_operational_series`'s
`ELEC.<KEY>.<facets>.<freq>` precedent. EIA gives this route no series id at all, so the
id is minted here (`coal_series_id`). Changing this scheme later orphans every row
already stored under the old one — do not change it without a migration plan.

## Why `source="coal"`, not `"eia"`

This is the first non-`eia` route on `EIAClient` — every other route on this client pulls
an EIA-sourced dataset with no reason to distinguish `source` further. `core.storage.
write_ts_long(df, source=...)` uses its `source` argument to choose the **partition
directory only**; it does not rewrite the frame's own `source` column. Before this
package, `get_facet_series` hardcoded `"source": "eia"` inside the DataFrame it built —
passing `source="coal"` to the writer while the client stamped `"eia"` on every row would
have produced rows filed under `coal/` whose own `source` column reads `eia`. Nothing
would raise, `read_ts_long(source="coal")` would still return them, and every freshness
query that groups by the `source` column would misreport them as `eia`. Fixed by adding a
`source: str = "eia"` parameter to `EIAClient.get_facet_series` (default keeps every
existing plan 31B caller — `pull_rto_demand`, `pull_rto_fuel_mix`, `pull_rto_interchange`
— byte-identical); `pull_coal.py` is the only caller that passes `source="coal"`.

## Units, verbatim per data key (Task 0, confirmed live)

- `receipts` → `"short tons"`
- `consumption` → `"short tons"`
- `stocks` → `"short tons"`
- `price` → `"dollars per short ton"`
- `heat-content` → `"average sulfur percent by weight"` — **wrong, see below.**

**Real, confirmed EIA-side bug, not a client parsing error**: `heat-content-units`
carries the literal same string as `sulfur-content-units`
(`"average sulfur percent by weight"`), even though `heat-content`'s real values
(`18.94`, `19.03`, `18.72` for the three most recent quarters checked) are in the
MMBtu-per-short-ton range, not a sulfur percentage (`sulfur-content`'s own real values
for the same quarters are `1.24`-`1.37`, a much smaller single-digit number). This
project's ingest-time convention stores units exactly as EIA publishes them,
unconverted, so `pull_coal.py` does **not** try to fix or override this unit string at
ingest time. A future task that surfaces `heat-content` on a chart must hardcode the
correct real-world unit (MMBtu per short ton) rather than trusting `heat-content-units`
verbatim.

## Deliberate exclusions

- **Coal Markets basin spot prices** (Powder River, Illinois, Appalachia) — S&P Global
  proprietary per EIA's own notice, with no bulk history anywhere. A chart built on them
  would be empty for months.
- **API2 and API4**, the seaborne thermal benchmarks that actually matter for European
  gas substitution, are never published by EIA at all — a vendor gap, not a backlog item.
  No amount of EIA-side work closes it.
- **Weekly coal production** — no API route carries it; would need scraping, out of
  scope for this package.
- **`sulfur-content` and `ash-content`** exist on this route (confirmed live, part of
  the same facet/data-key set as the five keys ingested) but are deliberately not
  ingested — they describe coal quality for emissions purposes, not the switching
  economics (quantity, price, heat content) this item exists for. Add them only with a
  reason.

## Item 4 — final gate, real pull outcomes, 2026-09-09

Real (not cassette) run against the live EIA API and the real lake:
`.venv/Scripts/python.exe -m pipelines.coal.pull_coal` — exit 0: `wrote 510 coal rows
across 5 series` (5 `DATA_KEYS` × ~102 quarters each; the pandas `dateutil`-fallback
`UserWarning` on `"YYYY-Qn"` period parsing is cosmetic, not a data error — every row
parsed to a real timestamp).

**The single most important check in this plan, confirmed live: `set(coal["source"])`
read back via a narrowed `read_ts_long(source="coal")` (never unbounded) is exactly
`{"coal"}`.** No row leaked through carrying `source="eia"` — `get_facet_series`'s
`source` parameter (see "Why `source=\"coal\"`, not `\"eia\"`" above) is working as
designed on real, not just cassette, data.

`series_id` set (5, one per `DATA_KEYS` entry, `US`+`98` only, matching the minted
scheme): `COAL.CONSUMPTION.US-98.Q`, `COAL.HEAT_CONTENT.US-98.Q`, `COAL.PRICE.US-98.Q`,
`COAL.RECEIPTS.US-98.Q`, `COAL.STOCKS.US-98.Q`. Units by series, read back from the real
lake, verbatim as EIA publishes them (unconverted, per this project's ingest-time
convention): `CONSUMPTION`/`RECEIPTS`/`STOCKS` → `"short tons"`; `PRICE` → `"dollars per
short ton"`; `HEAT_CONTENT` → `"average sulfur percent by weight"` — the same real
EIA-side mislabelling documented above, reproduced again here on live data rather than
fixed at ingest time.

**Full suite, lint and types**, run after this pull (shared with items 5/6's own
verification — see `pipelines/eia/NOTES.md` Task 4): 773 passed, 1 failed (the known,
out-of-scope `02_gas_storage.py`/GIE `deviation` KeyError, untouched by this package), 16
deselected. `ruff check .` clean. `mypy core pipelines infra` — no issues found in 167
source files, **the first time `pipelines/coal/` has been checked under mypy** (it is a
new package under an already-checked path) — zero errors.
