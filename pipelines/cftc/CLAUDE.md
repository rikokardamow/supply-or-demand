# pipelines/cftc — Claude Code Guide

## Real source, confirmed live — not the legacy PDF/text reports

Spec 19's own text assumed CFTC COT data already existed via "Spec 14" — confirmed live
this session that it does not (no pipeline, no series anywhere in the lake; Spec 14 was
never built). CFTC's own COT landing page
(`https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm`, fetched live) points
to the **Public Reporting Environment** (`publicreporting.cftc.gov`) as its current
API/bulk-download access point, alongside the legacy flat-file reports
(`/dea/newcot/f_disagg.txt` etc.) and the "Historical Compressed" zip archives. This
pipeline uses the PRE's own Socrata dataset directly (`BASE_URL` in `client.py`) rather
than parsing a flat-file or a zip archive — a real, structured, paginated REST API, no
API key required (confirmed live via unauthenticated `curl`).

## Dataset: `72hh-3qpy` — Disaggregated Futures-Only report

Confirmed live via a direct query (`curl .../72hh-3qpy.json?$limit=3`): weekly report data
back to 2006, one row per (contract, report date). Real columns used here:
`report_date_as_yyyy_mm_dd`, `cftc_contract_market_code`, `m_money_positions_long_all`,
`m_money_positions_short_all` (managed money), `prod_merc_positions_long`,
`prod_merc_positions_short` (producer/merchant), `open_interest_all`. **Every value comes
back as a string** (even numeric fields) — `client.py` casts explicitly, never assumes
Socrata's own JSON typed the column.

**Real field-name quirk, confirmed live, not "fixed" as a typo**: the swap-dealer short
column is genuinely double-underscored in CFTC's own schema —
`swap__positions_short_all` — this pipeline doesn't use that field, but any future session
reading this dataset should expect it, not assume a single underscore.

## Real contract codes, confirmed live (not guessed from a name)

| Root | Code | Real `contract_market_name` | Confirmed |
|---|---|---|---|
| `cl` | `067651` | WTI-PHYSICAL | live grouped query against the dataset |
| `rb` | `111659` | GASOLINE RBOB | live grouped query against the dataset |
| `ho` | `022651` | NY HARBOR ULSD | live grouped query against the dataset |
| `lco` | `06765T` | BRENT LAST DAY | live grouped query **and** a direct spot-check (real OI ~270k contracts, `commodity: CRUDE OIL`, `contract_units: CONTRACTS OF 1,000 BARRELS`, most recent report date matching the current week) |

`lco`'s own `cftc_market_code` comes back `"NYME"` rather than an ICE-specific code — a
real CFTC reporting quirk (ICE Brent futures are CFTC-regulated and reported through the
NYMEX-grouped reporting umbrella for US regulatory purposes), not a data error; confirmed
correct via the direct spot-check above before trusting it for real series.

## Weekly-only, not daily

CFTC COT publishes once a week (data as of Tuesday, released Friday 15:30 ET — already in
root `CLAUDE.md`'s own release calendar as `cftc_cot`, matching `core/calendars.py`'s
existing `RELEASES["cftc_cot"]` entry). `pull_weekly.py` (not `pull_daily.py`, matching
`pipelines/baker_hughes/pull_rigs.py`'s own semantic-naming precedent) re-pulls a trailing
8-week window — idempotent via `write_ts_long`'s own `(series_id, ts)` de-dup. Registered
in `infra/run_scheduled.py`'s `weekly_fri` cadence group, alongside `baker_hughes`/`macro`/
`adanos`.

## No settings/API key needed

Confirmed live: unauthenticated Socrata queries at this volume (4 contracts x ~1000 weekly
rows each, paginated 5000/page) work without an `X-App-Token`. Revisit only if real
throttling is ever observed — Socrata rate-limits unauthenticated apps harder than
token-holding ones, but nothing in this pipeline's own usage pattern should trip that.

## Verified (Spec 19 Session A)

`pull_history.py` run for real: confirms real row counts for all 4 roots. One real
managed-money net-length figure spot-checked directly against this same PRE dataset for a
specific report date (the report's own source of truth — not a PDF scrape, since the PRE
*is* CFTC's own current, authoritative access point for this same data).
