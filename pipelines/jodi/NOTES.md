# pipelines/jodi — notes

## No API, no key — a bulk annual CSV download
`https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/` +
either `{year}.csv` (a closed, prior year) or `primaryyear{year}.csv` (the current,
still-in-progress "year to date" year) — **two different filename patterns, confirmed
live**, not a single guessable one. The current year's file is what JODI updates monthly
(per the spec's own "~20th" release note), so it's always re-downloaded, never served from
cache (`client.py::download_annual_csv`) — closed years are cached indefinitely once
fetched, mirroring `pipelines/opec_momr`'s raw-file-caching precedent
(`data/raw/jodi/jodi-primary-{year}.csv`).

## Two annual tables exist — "primary" and "secondary" — both are read
Confirmed live via JODI's own "A Guide on JODI-Oil World Database Item Names" PDF: the
**primary** table covers crude oil (+ NGL + other crude), with flow codes like `INDPROD`
("Production"), `REFINOBS` ("Refinery intake"), `CLOSTLV` ("Closing stocks"). The
**secondary** table covers *refined products* (LPG, naphtha, gasoline, gas/diesel, fuel
oil...) with a different flow vocabulary (`REFGROUT`, `RECEIPTS`, `TOTDEMO`...).
`pull_jodi.py` reads the primary table for crude. `pull_demand.py` reads the **secondary**
table for total product demand — `TOTDEMO` / `TOTPRODS` / `KBD`, monthly per country,
confirmed live 2026-10-10 — for the US, China and the twenty euro-area members, from 2012.
It is the consumption side of `core/oil_demand.py`. In that slice the only non-numeric
marker seen is `-`. Malta has gaps (2015-09 → 2016-01, 2017-05); the latest month is
routinely missing one or two smaller members.

## Confirmed real column schema
`REF_AREA` (ISO 3166-1 alpha-2 country code), `TIME_PERIOD` (`yyyy-mm`), `ENERGY_PRODUCT`
(`CRUDEOIL` for this pipeline), `FLOW_BREAKDOWN` (see above), `UNIT_MEASURE` (`KBD`/`KBBL`/
`KL`/`KTONS`/`CONVBBL`), `OBS_VALUE` (a **string** column — see below),
`ASSESSMENT_CODE` (1-4, a data-quality flag; not filtered on here — even
"3 = not assessed" rows are kept, since that's the default/common case, not a
sign of a bad value).

## `OBS_VALUE` — two distinct non-numeric markers, both mean "skip"
Confirmed live: `"-"` means genuinely not reported for that country/period/flow/unit
combination; `"x"` means confidential or the unit doesn't apply (e.g. a stock *level*
reported under a rate unit like `KBD` comes back `"x"`, not a real number — `CLOSTLV` is
only meaningful under `KBBL`). Both are dropped before `pd.to_numeric`, not treated as
zero or an error.

## Unit choice per flow — confirmed live, not arbitrary
`INDPROD`/`REFINOBS` are rate flows (production/intake per day) → `KBD` (thousand
barrels/day, stored as `"kb/d"`). `CLOSTLV` is a stock *level*, not a rate → `KBBL`
(thousand barrels, stored as `"kbbl"`) is the one that actually carries real values;
`KBD` for `CLOSTLV` comes back `"x"` (confirmed live), matching the point above.

## Top-15 producers — computed from JODI's own real data, not assumed
**A genuine, confirmed reporting gap**: Russia, Iraq, Iran, UAE, and Brazil — all major
real-world crude producers — have **zero** `INDPROD` rows in JODI's primary table for all
of 2026. This isn't a bug in this pipeline; it's a well-known real limitation of JODI's
voluntary self-reporting model (some of the largest producers don't report crude
production through this specific channel). Ranking by a single latest month would also be
skewed by occasional one-off gaps for otherwise-reporting countries — `TOP_15_PRODUCERS`
in `pull_jodi.py` was computed by averaging each country's `CRUDEOIL`/`INDPROD`/`KBD`
value across every available 2026 month (not just the latest), then taking the top 15:
`US, SA, CN, CA, NO, MX, KZ, KW, NG, VE, DZ, GB, IN, ID, MY`. This is the real, achievable
top-15 from JODI's own data — not an idealised list assembled from other sources. Revisit
if Russia/Iraq/Iran/UAE/Brazil ever start reporting `INDPROD` again.

**A handful of (country, flow) combinations are still genuinely absent** even within this
top-15 set: China, Kazakhstan, and Malaysia have no `CLOSTLV` (closing stocks) data, and
Kazakhstan additionally has no `REFINOBS` (refinery intake) data — 41 of the 45 possible
(15 countries × 3 flows) series exist, not all 45. Not an error; those countries simply
don't report those specific flows through JODI's primary channel.

## Series id / geo convention
`jodi.{flow_slug}.{country_code_lower}` (`crude_production`/`refinery_intake`/
`closing_stocks`), `geo` = the raw ISO alpha-2 code (e.g. `"US"`, `"SA"`) — matching this
project's general `{source}.{field}.{qualifier}` convention.

## revision_date
JODI's CSV carries no per-row revision/last-updated timestamp (same situation as
`pipelines/eia`) — `revision_date` is stamped at ingestion time. Re-running the monthly
entrypoint is naturally idempotent via `write_ts_long`'s revision-based de-dup: verified
live, running `pull_jodi.py` twice in a row left the row count unchanged (706 rows).

## History depth
`CURRENT_YEAR_HISTORY_DEPTH = 2` (current year + 1 prior closed year) — enough for a
meaningful trend without looping through all 25 years of annual files JODI publishes back
to 2002 (a full historical backfill wasn't in this session's scope; only "monthly
entrypoint" was asked for). Increase this constant later if deeper history is needed for a
specific chart.

## Verified (Session C)
Real pull: 706 rows across 41 series (15 countries × 3 flows, minus 4 genuinely-missing
combinations) from 2 years of the primary CSV. Idempotency confirmed live: identical row
count across two consecutive runs. Tests use a small synthetic CSV fixture (monkeypatched
`requests.get`), not the real ~4.7 MB annual file — avoids a large fixture while still
exercising the real filtering/reshaping logic (`pull_jodi.py::filter_and_transform`,
extracted specifically to be testable this way) and the real caching behaviour
(`client.py`, current-year-always-refetches vs. closed-year-cached-forever).
