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
`requests.exceptions.HTTPError` with no built-in retry. `ENTSOEClient._request_with_retry`
adds exponential backoff (capped 60s, 5 attempts) specifically for 503/5xx, same pattern as
`pipelines/eia`/`pipelines/gie`.

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
