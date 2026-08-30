# pipelines/entsoe — notes

## Client library
Uses `entsoe-py` (PyPI, v0.8.0 confirmed current) rather than raw REST — the Transparency
Platform is genuinely flaky (see below), and `entsoe-py` already handles the XML parsing and
zone-name → EIC-code mapping. `pipelines/entsoe/client.py`'s `ENTSOEClient` wraps
`EntsoePandasClient`, not `EntsoeRawClient` — the pandas client returns a ready-made
`pd.Series`/`pd.DataFrame` instead of raw XML. Import from `entsoe.entsoe`, not the
top-level `entsoe` package — `EntsoePandasClient` isn't in `entsoe/__init__.py`'s explicit
exports, which mypy (strict mode) flags if imported from the package root.

`entsoe-py` parses the platform's XML responses with `BeautifulSoup(..., "html.parser")`
internally, which throws a harmless `XMLParsedAsHTMLWarning` on every call (its own choice,
not something to fix here) — visible in test output, not a real problem.

## Auth
`securityToken` **query parameter** (not a header) — `EntsoePandasClient(api_key=...)` adds
it automatically to every request, from `settings.entsoe_api_key`.

## Never print a raw exception from this client
Confirmed live (2026-08-30): `requests.exceptions.HTTPError`'s default string representation
embeds the **full request URL**, including `securityToken` — printing `str(exc)` while
debugging a 503 leaked the real API key into a chat transcript. `ENTSOEClient` converts every
HTTP error to a bare `RuntimeError(f"... HTTP {status}")` before it can propagate, and nothing
in this package should ever `print(exc)`/`str(exc)` on an exception from `entsoe-py` or
`requests` directly — extract only the status code.

## The Transparency Platform is genuinely flaky — confirmed live, not assumed
Repeating the *identical* day-ahead-price query for DE_LU minutes apart returned `200` once
and `503` (an HTML page, not a JSON/XML error body) another time. Querying 4 zones with a
few seconds' pacing got a mix of `200`/`503` with no pattern by zone. `entsoe-py`'s own
`@retry` decorator (`entsoe.decorators.retry`, confirmed by reading its source) only catches
connection-level errors (`ConnectionError`, DNS failures, `RemoteDisconnected`) — it does
**not** retry on HTTP error status codes, so a 503 propagates immediately as
`requests.exceptions.HTTPError` with no built-in retry. `ENTSOEClient._call`
adds exponential backoff (capped 60s, 5 attempts) specifically for 503/5xx, same pattern as
`pipelines/eia`/`pipelines/gie`.

**No default timeout — confirmed live, this actually hung a pull** (Session B):
`EntsoeRawClient.__init__` defaults `timeout=None` (confirmed by reading its source), passed
straight through to `requests.get(..., timeout=None)` — meaning no client-side timeout at
all. A Session B pull hung indefinitely on one zone with no exception ever raised (so the
503 retry logic never even triggered, since nothing failed — it just never returned).
Killed by hand after confirming no orphaned process remained. Fixed by passing
`EntsoePandasClient(api_key=..., timeout=REQUEST_TIMEOUT_SECONDS)` explicitly (45s, matching
`pipelines/gie`'s own timeout choice) and catching `requests.exceptions.RequestException`
(timeouts, connection errors — anything with no response at all) alongside `HTTPError` in
the retry loop, not just HTTP status codes.

## Zone EIC codes (Session A) — confirmed live via `entsoe.mappings.Area` and real queries
| Zone | EIC code | Resolution confirmed live |
|---|---|---|
| DE_LU | `10Y1001A1001A82H` | 15-minute (`PT15M`) — 8,641 rows for a 90-day pull |
| FR | `10YFR-RTE------C` | 15-minute — 8,641 rows |
| NL | `10YNL----------L` | 15-minute — 8,641 rows |
| IE_SEM | `10Y1001A1001A59C` | **hourly** — 2,137 rows (≈90×24) — confirms resolution is genuinely per-zone, not something to hardcode |

`entsoe-py`'s `Area` enum accepts these exact strings (`Area["DE_LU"]` etc. — no translation
needed, `ENTSOEClient.get_day_ahead_prices(zone, ...)` passes the zone string straight
through to `query_day_ahead_prices`).

## Resolution is per-zone, not fixed — don't assume hourly
`specs/04_entsoe-eu-power.md`'s data model already flags `freq='H' or '15T'` — confirmed
live this isn't hypothetical: DE_LU, FR, and NL all came back 15-minute, not hourly (many EU
markets moved to 15-minute settlement). `ENTSOEClient._infer_freq` reads the actual spacing
between the returned index's first two points rather than hardcoding a resolution per zone.

## Timestamps
`entsoe-py` returns a **tz-aware, zone-local** `DatetimeIndex` (e.g. `Europe/Berlin` for
DE_LU) — `ENTSOEClient.get_day_ahead_prices` converts to naive UTC
(`.tz_convert("UTC").tz_localize(None)`) before returning, matching every other pipeline's
`ts_long` convention. Don't just take a date substring here like `pipelines/entsog` does —
unlike ENTSOG's daily gas-day values, day-ahead power prices are genuinely time-of-day
granular (15-min/hourly), so the actual UTC instant matters, not just the calendar date.

## revision_date
Day-ahead prices are auction-cleared and published once — not revised afterwards (unlike
EIA/GIE actuals) — so `revision_date` is stamped at ingestion time, same reasoning as
`pipelines/eia`'s note (real revision info isn't available, ingestion time is the best proxy,
though here it's arguably moot since the underlying value itself doesn't change).

## Series id convention
`entsoe.{zone}.day_ahead_price`, `unit="EUR/MWh"`, `geo={zone}` — matches the
`{source}.{geo}.{field}` pattern already used by `pipelines/gie`.

## Verified (Session A)
90-day pull: DE_LU/FR/NL 8,641 rows each (15-min), IE_SEM 2,137 rows (hourly) — 28,060 rows
total. Real value ranges are plausible EU day-ahead prices, including negative prices at
times (DE_LU/FR/NL: -52.99 to 747-902 EUR/MWh; IE_SEM: 5.54-407 EUR/MWh, no negatives
observed in this window). Acceptance criterion met: yesterday's DE_LU price cross-checked
against an independent fresh API call — exact match across all 89 points that day (max
diff 0.0 EUR/MWh).

**Credential-handling incident during planning**: printed a raw `requests.HTTPError` while
testing the 503 flakiness before any code existed — its `str()` embedded the full request
URL including the real `securityToken`. Disclosed immediately, user asked to rotate the key.
See "Never print a raw exception from this client" above for the resulting rule, and the
memory file `credential_handling_incidents.md` for the full incident record.

## Session B — generation, load, wind/solar forecast, cross-border flows, page + maps

**Per-item resilience, not just per-request retry**: even with the timeout fix and 503
backoff, a 13-zone (or 12-border) pull run still routinely has 1-3 items fail after
exhausting retries — the platform's flakiness is real and sustained, not a rare blip. Every
pull script (`pull_prices.py`, `pull_actuals.py`, `pull_flows.py`) catches `RuntimeError` per
zone/border/indicator individually, prints `"{item}: FAILED (...) — skipping"`, and continues
— one flaky item must never abort an otherwise-successful multi-item pull. Re-running the
same script again picks up whatever failed last time (`write_ts_long`/`write_flows`'s
de-dup makes this idempotent) — confirmed live: two consecutive `pull_prices.py` runs each
failed on a *different* random set of 2-3 zones, and the union of both runs' successes
covered 12 of 13 zones cleanly.

**GB has a real, confirmed data gap across every indicator** — day-ahead prices, load,
generation, and wind/solar forecast all returned genuinely empty results (not 503s, not
timeouts — a clean empty `DataFrame`/`Series`, the `NoMatchingDataError` path). This isn't
flakiness; it's very likely GB's post-Brexit reporting status to ENTSO-E (no longer full EU
internal-market obligations) — matches the spec's own "GB (as available)" phrasing
precisely, so this was anticipated, not a bug. GB's cross-border flows *into* other zones
(`FR -> GB`, `NL -> GB`, `IE_SEM -> GB`) do have real data — it's GB's own zone-level
indicators that are missing, not its interconnectors.

**IE_SEM's load is also empty** (generation and wind/solar forecast both work fine for
IE_SEM) — almost certainly because Ireland's demand/load data is published through EirGrid's
own systems (Session C's data source) rather than duplicated to ENTSO-E's load indicator.
Not a gap to solve here; Session C's EirGrid panel is exactly where Irish demand comes from.

**`SE_4 <-> DK_1` cross-border flow has no data in either direction** — confirmed live by
querying both `SE_4->DK_1` and `DK_1->SE_4` explicitly, both empty. Every other border in
`zones.py::BORDERS` (11 of 12) has real data, comfortably past the spec's ≥8 minimum, so this
wasn't chased further — either this specific pair isn't a distinct ENTSO-E-tracked
cross-border point, or it's aggregated under a different registered pairing.

**Final zone/border coverage** (after 2 pull runs each, unioned): 12 of 13 zones have real
day-ahead prices (all but GB); 11 of 13 zones have real load (all but IE_SEM/GB); 12 of 13
zones have real generation and wind/solar forecast data (all but GB); 11 of 12 mapped
borders have real cross-border flow data (all but `SE_4<->DK_1`).

**Page `04_eu_power.py`**: price map (`components/power_maps.py::render_price_map` —
Scattergeo markers at representative zone coordinates, diverging navy-to-red colourscale by
latest price), cross-border arrow map (`render_flow_map`, same line+triangle technique as
`padd_map.py`/`entsog_map.py`), a selectable-zone generation-mix stacked area
(`core.theme.generation_mix_chart`, new — a documented PSR-type colour exception to the
4-colour house palette per the spec's own "renewables greens/blues, thermal greys/navy"
instruction), residual load (`transforms.py::residual_load`, load minus wind minus solar),
and a ranked net-position bar (`transforms.py::net_position`, generalised from
`pipelines/eia/transforms.py::net_balance`'s identical inbound/outbound pattern).

**Generation mix keeps only "Actual Aggregated" columns** — `query_generation`'s response
has MultiIndex columns per PSR type, and Hydro Pumped Storage has *both* an "Actual
Aggregated" column (generation) and an "Actual Consumption" column (charging demand,
confirmed live) — only the former belongs in a generation-mix chart. `get_generation` drops
the latter before melting to long format.

## Session D — pull_daily.py, and a real data-loss bug found via the idempotency check

`pull_prices.py`/`pull_actuals.py`/`pull_flows.py` each now expose a `pull_*()` helper
(same per-item resilience, just returning a DataFrame instead of writing it) so
`pull_daily.py` can reuse them with narrower windows rather than duplicating the
per-zone/per-border loops. Their `main()`s are unchanged one-off full backfills
(90/14/90 days).

`pull_daily.py` is the actual scheduled entrypoint (Spec 13): day-ahead prices for
`[today-1, today+2)` (ENTSO-E publishes day D+1's prices ~12:45 CET on day D, per root
NOTES.md's release calendar — the window covers a run any time of day, with a
one-day margin either side) plus actuals (load, generation, wind/solar forecast,
cross-border flows) for the prior day only, per the spec's own Session D scope.

**Prices/load/generation/wind-solar-forecast need no revision-window logic at all** —
day-ahead prices are never revised (see this file's `revision_date` note above) and
`write_ts_long` already keeps the latest-`revision_date` row per `(series_id, ts)`, so
re-pulling an overlapping window is naturally idempotent for free.

**Cross-border flows are the one exception, and re-pulling them exposed a real bug**:
`flows` (per `core/schemas.py`) has no `revision_date` column, so — same as
`pipelines/entsog`'s Session D — a daily re-pull needs `write_flows`'s
`replace_window` to avoid double-counting a revised value. But `replace_window`
previously dropped **every** existing row in the window regardless of which
`(from_node, to_node)` pair it belonged to. Combined with the per-border resilience
pattern (one flaky border must never abort the rest), a border whose fetch failed on
a given run was simply absent from that run's `df` — and `replace_window` had already
deleted its still-good prior data for the window, replacing it with nothing.

**Caught live, not hypothetically**: running `pull_daily.py` twice in a row, `DE_LU
-> NL` succeeded on run 1 (96 rows) but hit a 503 on run 2 and was skipped — after
run 2, `read_flows` showed **zero** rows for `DE_LU -> NL` in that window, confirming
real data loss, not just a stale-but-present row. Fixed at the storage layer:
`core.storage._write_partitioned`'s `replace_window` handling now scopes the
in-window deletion to only the `(from_node, to_node)` pairs actually present in the
DataFrame being written — a pair missing from this run's pull keeps its existing data
untouched instead of being wiped. Added
`tests/test_storage.py::test_write_flows_replace_window_keeps_pairs_missing_from_the_fresh_pull`
as a regression test. This fix also applies to `pipelines/entsog`'s identical
`pull_daily.py` pattern, which had the same latent (if less frequently triggered) risk.

**Verified**: after the fix, a third `pull_daily.py` run re-fetched `DE_LU -> NL`
successfully (88 rows for the trailing window) and every other border that had data
before the fix still had it — `read_flows` confirmed no border was lost across the
repair run. Idempotency now holds in the sense that actually matters for a
confirmed-flaky API: a failed item on any given run leaves prior data untouched
rather than either duplicating it or deleting it.
