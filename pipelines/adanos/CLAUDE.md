# pipelines/adanos — Claude Code Guide

## Real API shape, confirmed live against the real key (not just the vendor's own docs)
`/compare` and `/trending/sectors` both match the vendor's own pasted documentation
exactly. `/trending/sectors` is a bare JSON array (not wrapped in an object), each
row carrying a `sector` field — `"Energy"` confirmed present live alongside
Information Technology, Consumer Discretionary, Communication Services, Financials,
Industrials, Health Care, Consumer Staples, Materials, Real Estate, Financial
Services, Utilities.

## Critical, confirmed-live gotcha: `/compare` never errors on an unrecognised ticker
A deliberately fake ticker (`NOTAREALTICKER123`) returned **HTTP 200** with a zeroed
row — `company_name: null`, `buzz_score: 0.0`, `sentiment_score: null` — identical in
shape to a genuinely-supported ticker that simply has no qualifying data this period.
The vendor's own docs describe a `400 Invalid compare item list` error for this case;
that never happened in practice. **The only real existence signal is a non-null
`company_name`** — `pull_adanos.py::pull_platform` filters on this, not on whether
the call itself succeeded.

## The ticker universe — all 57 confirmed live, one real wrong guess caught
Every ticker in `tickers.py::TICKERS` was verified via a real `/compare` call before
being trusted — **all 57 resolved with a real `company_name`**, including all 5
OPEC/OPEC+ geographic-exposure candidates (`GENL`, `GKP`, `OANDO`, `ARADEL` resolved
on the first try). **One real wrong guess, caught via `/search`**: Seplat Energy's
initially-assumed ticker `SEPL` (its LSE ticker) returned `company_name: null` in
`/compare` — a live `/search` for "Seplat" found the real Adanos symbol is
**`SEPLAT`**, confirmed via `exchange: "NGX"`, `country: "Nigeria"`, `sector:
"Energy"`. No other ticker needed correcting.

## Real coverage gap, confirmed live — not a bug
The 5 OPEC/OPEC+-exposure tickers are all *recognised* (real `company_name`) but show
**genuinely near-zero Reddit/Polymarket activity** — confirmed live: `GKP`, `SEPLAT`,
`OANDO`, `ARADEL` all returned `buzz_score: 0.0`, `sentiment_score: null` across
Reddit. `GENL` was the one exception with any real signal at all: 1 real News mention
(`sentiment_score: 0.345`, positive) in the same live check, still zero on Reddit.
This matches the expectation stated in specs/17_adanos-sentiment-overlay.md — Adanos's
whole product is built around Reddit/X *retail* sentiment, which is overwhelmingly a
US-market phenomenon, and these are LSE/NGX-listed frontier-market producers. Kept in
the pipeline regardless: real, if usually zero, data is still correctly represented
(as a zero, not silently dropped), and any future spike (a real Kurdistan deal, a
Nigerian sector event) would be caught rather than missed.

## `sentiment_score` is nullable — handled by skipping the row, not writing a fake 0.0
Confirmed live: any ticker/platform pair with no qualifying directional signal this
period returns `sentiment_score: null` (not 0.0 — 0.0 is itself a real, meaningful
"neutral" reading elsewhere in the data). `ts_long`'s own `value` column requires a
real float, so `pull_adanos.py::pull_platform` skips writing a sentiment_score row
entirely when null, rather than fabricating a misleading `0.0` that would read as
"neutral" instead of "no data". `buzz_score` has no such gap — it is always a real
float (0.0 when there is genuinely no activity), so it is always written.

## Request budget — confirmed live, matches the spec's own arithmetic exactly
A real full weekly pull used **exactly 25 calls** (6 batches × 4 platforms + 1
sector-trend call, per `specs/17_adanos-sentiment-overlay.md`'s own arithmetic),
confirmed via `X-RateLimit-Remaining-Monthly` dropping by exactly 1 per call with no
surprises. `X-RateLimit-Remaining-Monthly` is logged after every call
(`pull_adanos.py`'s own print statements) specifically so real monthly usage against
the 250/month free-tier cap stays visible without needing to check the Adanos
dashboard separately.

## Verified (Session A)
A real `pull_adanos.py` run wrote **372 rows** (X: 107, News: 105, Reddit: 103,
Polymarket: 57 — Polymarket's own low count reflects genuinely thin prediction-market
coverage of most single-stock energy names, not a bug) across all four platforms plus
the sector trend, using exactly the documented 25-call budget. All three page-10
visuals confirmed live in-browser with real data: buzz-by-platform (4 lines, one per
platform), latest-sentiment-by-ticker (a 12-ticker grouped bar, Polymarket bars
correctly absent for tickers with null sentiment there), and the Reddit
Energy-sector buzz trend line — plus the honesty-rule Kardamow-take caption. Only a
single data point exists per series so far (this is the first-ever pull); the charts
will show real trend lines once a second week's pull lands.
