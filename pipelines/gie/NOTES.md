# pipelines/gie — notes

## Auth
`x-key` **header** (not a query param), value from `settings.gie_api_key`. Never log/print
the header dict or a full request — same discipline as `pipelines/eia/NOTES.md`'s secrets
section documents for EIA's `api_key`.

## Endpoint & pagination
`GET https://agsi.gie.eu/api` with `country` (ISO 2-letter, case-sensitive uppercase for
member states — e.g. `DE`, not `de`), `from`, `to` (`YYYY-MM-DD`), `page`. Response:
`{last_page, total, dataset, gas_day, data: [...]}`, sorted newest-first. **Fixed 30
rows/page** — confirmed live (DE 2018-2026 → `last_page: 106`). Loop `page` from 1 until
`page >= last_page`.

## Rate limiting
No `Retry-After` header observed on a normal 200 response — GIE's documented ~60s cool-off
isn't header-driven, so `GIEClient._get` uses defensive exponential backoff (capped 60s) on
429/5xx responses, plus a flat pacing delay between pages/countries in `pull_agsi.py` as a
courtesy (not because a block was ever triggered — don't test this by deliberately flooding
the API).

**Real gotcha hit during the actual ~530-request pull**: a plain read timeout
(`requests.exceptions.ReadTimeout`) happened mid-run — this raises *before* a `Response`
object exists, so status-code-based retry logic alone never sees it and the whole pull dies.
`_get` wraps the request itself in `try/except requests.exceptions.RequestException` with the
same backoff, not just the status-code check after a response comes back. Timeout bumped
30s → 45s too (one single-page request took ~20s during normal cassette recording, so 30s
had little margin).

## revision_date — real, unlike EIA
Every row has `updatedAt` (e.g. a gas-day's figures get revised ~2 days later) — a genuine
per-row revision timestamp GIE provides directly, unlike EIA (see
`pipelines/eia/NOTES.md`'s `revision_date` note, which uses ingestion time because EIA
gives nothing better). `GIEClient` uses `updatedAt` as `revision_date`, so
`write_ts_long`'s revision-based de-dup naturally keeps the latest published revision, not
just the latest pull.

## Field mapping
Each AGSI row maps to 5 `ts_long` rows, `series_id = agsi.{COUNTRY}.{field}`:
- `full` → `full_pct` (`%`)
- `gasInStorage` → `gas_in_storage` (`TWh`)
- `injection` → `injection` (`GWh/d`)
- `withdrawal` → `withdrawal` (`GWh/d`)
- `workingGasVolume` → `working_gas_volume` (`TWh`)

`net_injection` (injection − withdrawal) is a **transform**
(`pipelines/gie/transforms.py:net_flow`), computed at read time — not stored, matching the
`pipelines/eia/transforms.py` pattern of deriving rather than pre-storing composite metrics.

Each ALSI row maps to 3 `ts_long` rows, `series_id = alsi.{COUNTRY}.{field}`:
- `inventory.lng` → `lng_inventory` (`1000 m3`)
- `sendOut` → `send_out` (`GWh/d`)
- `dtmi.lng` → `dtmi` (`1000 m3`)

## Countries pulled
**Session A** picked a top-5 by working gas volume (`DE` 246.5 TWh, `IT` 203.4, `NL` 143.8,
`FR` 123.9, `AT` 100.3 — chosen empirically, not guessed) using `get_agsi_history()`
(per-country, main `/api` endpoint). **Session B superseded this** for the actual pull
scripts — see "EU aggregate" below — `get_agsi_history()` itself is untouched and still a
valid one-off single-country method, just no longer what `pull_agsi.py` uses for bulk
history.

## EU aggregate — solved in Session B via the `children` tree, not per-country pulls
`country=eu` (or `EU`) on the main `/api` endpoint returns `total: 0` — not a valid value
there. The real EU (and `"ne"` = Non-EU) aggregate lives at `GET https://agsi.gie.eu/api/eu`,
which only accepts a **singular `date`** param (one gas-day snapshot per call), not
`from`/`to`+`page`.

**Key discovery**: that same `/api/eu?date=X` response nests **every EU member country's own
full data** under the `"eu"` row's `"children"` array (20 countries, 2-letter codes) — and
`"ne"`'s children give Serbia/Ukraine/post-Brexit UK (not pulled — out of scope, EU-focused
per the spec). One date-loop call therefore yields EU aggregate + every member country in a
single pass, which is why `GIEClient._get_eu_tree_history()` (shared by
`get_agsi_eu_tree_history()` and `get_alsi_eu_tree_history()`) is the actual mechanism
`pull_agsi.py`/`pull_alsi.py` use — not `get_agsi_history()`'s per-country pagination.
Verified: 304,035 rows across EU + 19 countries for AGSI, matching values cross-checked
against independent live calls exactly.

**This costs real wall-clock time**: ~3,163 daily calls, sequential (one date at a time, no
concurrency — respecting the spec's rate-limit caution), each ~0.5-0.65s in isolated testing
but **1.5-2x slower in the actual full run** (AGSI: ~56 min real vs ~35 min estimated; ALSI:
~98 min real vs ~64 min estimated at the halfway mark) — budget generously, don't trust a
short sample's rate to extrapolate the full run.

**Buffering gotcha**: added progress-logging `print()` calls to `_get_eu_tree_history` so a
long pull isn't a silent black box — but a background run redirecting stdout to a file
showed *zero* output for ~20 minutes despite real CPU activity, because Python block-buffers
stdout when it isn't a TTY. Fixed with `print(..., flush=True)` **and** running the script
via `python -u` (belt-and-suspenders — either alone would have sufficed, both cost nothing).
If you add more progress logging anywhere in this package, use `flush=True` on it.

## ALSI+ (LNG)
Endpoint `https://alsi.gie.eu/api`, same `x-key` auth and same `/api/eu`+`children` tree
mechanism as AGSI. Response nests `inventory`/`dtmi` as `{"lng": ..., "gwh": ...}` — `.lng`
is used (matches the spec's `lngInventory` naming), confirmed against alsi.gie.eu's own
published units ("10³ m³ LNG"), not `.gwh` (energy-equivalent). **Landlocked EU countries
have no LNG data** — e.g. Austria's ALSI row comes back with every field as the literal
string `"-"` and `status: "N"`; `_is_missing()` drops those fields entirely rather than
storing a fake zero. Verified: 111,756 rows across EU + 13 LNG-terminal countries.

## Provisional vs. revised data — pull_daily.py (Session C)
`pull_agsi.py`/`pull_alsi.py` are one-off **full historical backfill** scripts (2018-present,
~3,163 requests each — see the wall-clock-time note above). `pull_daily.py` is the actual
entrypoint meant for scheduled/orchestrated runs (Spec 13): it re-fetches only the **trailing
5 days** (`TRAILING_DAYS`) for both AGSI and ALSI, relying on `write_ts_long`'s
revision-based de-dup (keeps the row with the latest `revision_date` per `series_id`+`ts`) to
pick up any late revisions GIE publishes for recent gas-days. Verified live: re-running it
refreshed `revision_date` (to a newer `updatedAt`) for every row inside the trailing window,
while a row just outside it (6 days back) kept its older `revision_date` untouched — exactly
the intended behaviour, and zero duplicate rows either way.

## Spec 32 — publishing to the Supabase serving layer (2026-09-09)

`publish_gie.py` publishes GIE into `serving.series_long` and `serving.seasonal` for the
Next.js UI (Spec 33). It **reads the lake, not a freshly-pulled frame** — `pull_daily.py`
only re-fetches a trailing 5-day window, so publishing its own output would put five days
into the serving copy and leave the seasonal band with nothing to compute from. Scheduled
in `infra/run_scheduled.py`'s `daily` group, *after* the `gie` pull it depends on.

**Live-verified 2026-09-09**: 416,357 rows across 142 series into `serving.series_long`,
and 51,830 rows across the same 142 series into `serving.seasonal` (142 × 365 day-of-year).
Both idempotent — re-running only appends to `serving.publish_log`.

**Two real defects the live data exposed, neither reachable from unit tests alone:**

1. **The current-year track was forward-filled into the future.** `core.seasonal`'s
   `_daily_ffill_by_year` fills every year onto a dense daily grid, which is correct for a
   completed year but fabricates the current one — it carries today's value flat to 31
   December. Confirmed live before the fix: `agsi.DE.full_pct` read **54.75% at doy 300 and
   doy 365**, both months away, which would have drawn a fake flat projection across the
   UI's seasonal chart. `serving.seasonal`'s own schema comment specifies `current` as
   "null if not yet". `core.publish.seasonal_rows` now blanks `current` after today's
   normalised day-of-year; `prior` is deliberately left filled across the whole curve,
   since a completed year genuinely holds its last value forward.
2. **Duplicate timestamps crash the seasonal maths.** `_daily_ffill_by_year` reindexes a
   ts-indexed series onto a daily grid, which requires unique timestamps —
   `ValueError: cannot reindex on an axis with duplicate labels` otherwise. GIE never hit
   this (it reads the already-deduped lake) but WPSR did, because it publishes its raw
   pulled frame and EIA's pagination returns a few boundary rows twice (see
   `pipelines/eia/NOTES.md`). Fixed in `core.publish.seasonal_rows` by deduping on `ts`
   first. **`core/seasonal.py` itself was deliberately not changed** — it is shared by
   every dashboard page, and cleaning the input is the serving layer's own job.

**What the published band actually says** (a real reading, not a smoke test):
`agsi.DE.full_pct` at doy 252 (9 September) — 7-year band 62.05–96.62%, median **87.57%**,
this year **54.75%**, last year 74.23%. German storage is not merely low against the
median, it is **below the 7-year minimum** for the date. `years = 7` confirms the band is
built from 2018–2025 with 2020 excluded, exactly as golden rule 4 requires.
