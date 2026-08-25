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

`net_injection` (injection − withdrawal) is a **transform**, computed at read time — not
stored, matching the `pipelines/eia/transforms.py` pattern of deriving rather than
pre-storing composite metrics.

## Countries pulled (top 5 by working gas volume, verified live 2026-08-23)
`DE` (246.5 TWh), `IT` (203.4), `NL` (143.8), `FR` (123.9), `AT` (100.3) — chosen empirically
by querying working-gas-volume and injection/withdrawal across 21 candidate countries, not
guessed. Next-largest was `HU` at 67.7 TWh, clearly a tier below. This overlaps but isn't
identical to the spec's own Session-B small-multiples list (`DE, NL, FR, IT, AT, PL`) — `PL`
(36.8 TWh) is smaller than all 5 pulled here.

## EU aggregate — different access pattern, not yet implemented
`country=eu` (or `EU`) on the main `/api` endpoint returns `total: 0` — it is **not** a valid
`country` value there. The real EU (and `"ne"` = Non-EU) aggregate lives at a separate
endpoint, `GET https://agsi.gie.eu/api/eu`, confirmed live — but that endpoint only accepts
a **singular `date`** param (one gas-day snapshot per call, both `eu` and `ne` rows
together), not `from`/`to` + `page`. Pulling full 2018-present EU history this way would mean
~3,140 individual daily requests. Not solved in Session A (out of scope — Germany-only per
the original spec text, expanded to the top-5 countries here, neither of which needed EU).
**Session B must decide**: pace ~3,140 single-day calls (slow, but uses the real EU number),
or compute an EU-equivalent by summing the pulled member countries (fast, but understates the
true EU-27 total since only 5 of the reporting countries are pulled — check whether the
`ne`/eu split and full EU-27 membership makes this materially inaccurate before choosing).

## ALSI+ (LNG) — not yet implemented
Endpoint is `https://alsi.gie.eu/api`, same `x-key` auth. Response nests `inventory` and
`dtmi` as `{"lng": ..., "gwh": ...}` sub-objects (confirmed live for `FR`) — pick `.lng` to
match the spec's `lngInventory`/`dtmi` naming (LNG volume units), not `.gwh` (energy units).
Not built yet — Session B's scope per the spec.
