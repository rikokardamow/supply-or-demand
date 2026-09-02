# pipelines/macro — Claude Code Guide

## Scope goes well beyond the spec's own 5-series list — by explicit user request
`specs/10_macro-fx.md` names 5 FRED series. Per explicit, repeated user instruction
during planning ("add many more data points from FRED... broader picture and unique
perspective... around Energy", then "include much more around energy and inflation
with micro and macro level"), `fred_series.py::FRED_SERIES` carries **35 series**,
split into `MACRO_SERIES` (18 — broad economy, inflation, rates) and `ENERGY_SERIES`
(17 — crude/product prices, energy-specific inflation, energy-sector labour/sentiment).
Every one was individually confirmed live (`Fred.get_series_info` + `get_series`)
before being added, not guessed from an ID/title — this is what caught the two real
mistakes below, not hypothetical caution.

## Two of the spec's/planning's own guesses were wrong — confirmed live, not assumed
- **`EA19CPALTT01GYM`** (the spec's own named EA HICP series): returns real data but
  is **stale — last point 2023-01-01**, over 3 years old. It's also the *wrong kind*
  of series for `deflate()`'s own use case — a YoY growth rate, not an index level
  (every other series in `FRED_SERIES` is an index level or a rate/percent, chosen
  deliberately). Replaced with **`CP0000EZ19M086NEST`** ("Harmonized Index of Consumer
  Prices: Total for Euro Area (19 Countries)", Index 2025=100, monthly, current
  through 2026-07) — found via `fred.search("euro area HICP inflation", ...)`.
- **`IR14260`**: looked like a plausible petroleum import-price index by ID pattern
  alone. It's actually "Import Price Index (End Use): **Zinc**". Replaced with the
  real one, found via `fred.search("petroleum import price index", ...)`:
  **`IR100`** ("Import Price Index (End Use): Petroleum Products, Excluding Natural
  Gas", Index 2000=100, monthly, current through 2026-07).

Two more candidates were investigated and dropped before ever reaching `FRED_SERIES`:
`GASMIDWW`/`GASGULFW`/`GASWSDW` (guessed PADD regional gasoline IDs) don't exist at
all — real IDs follow a different pattern (`GASREG{region}W`, found via
`fred.search(...)`); `IPG211111CS` (oil/gas mining industrial production) exists but
is stale (last point 2021-04-01).

## `FRED_SERIES` — full reference table (unit/freq/geo, all confirmed live)

**Macro (18)**: `CPIAUCSL` (US CPI), `CPILFESL` (US core CPI), `PCEPI`/`PCEPILFE` (PCE
price index, headline/core — the Fed's own preferred gauge), `CP0000EZ19M086NEST` (EA
HICP), `PPIACO` (PPI all commodities), `DTWEXBGS`/`DTWEXAFEGS` (broad / advanced-
foreign-economies USD indices), `DGS10` (10Y nominal yield), `DFII10` (10Y real/TIPS
yield — pairs directly with `DGS10` for the spec's own "real vs nominal" theme without
needing `deflate()` at all for rates), `T5YIE`/`T10YIE` (5Y/10Y market-based breakeven
inflation), `MICH` (U. Michigan survey-based inflation expectations), `INDPRO`
(industrial production), `GDPC1` (real GDP), `UNRATE` (unemployment), `FEDFUNDS` (Fed
funds rate), `M2SL` (M2 money supply).

**Energy (17)**: `DCOILWTICO` (WTI spot), `DCOILBRENTEU` (Brent spot — **the only
Brent series anywhere in this project**, everything else is WTI-only via EIA),
`DHHNGSP` (Henry Hub spot), `GASREGW` (US national regular gasoline) plus
`GASREGECW`/`GASREGMWW`/`GASREGGCW`/`GASREGRMW`/`GASREGWCW` (PADD I-V regular
gasoline — complements `pipelines/eia`'s own PADD-level crude/product *stocks* with
PADD-level *prices*, `geo` values `PADD1`-`PADD5` matching that pipeline's own
convention), `DDFUELUSGULF`/`DJFUELUSGULF` (Gulf Coast diesel/jet fuel — the latter
complements `pipelines/eia/pull_wpsr.py`'s `WKJUPUS2`), `WPU0561` (PPI crude petroleum,
domestic production — confirmed genuinely distinct from `PPIENG` below, not a
duplicate under two IDs), `PPIENG` (PPI fuels & related products/power, broader
aggregate), `CPIENGSL` (CPI energy component), `IR100` (import price index,
petroleum), `CES1021100001` (oil & gas extraction employment — a micro/labour-market
angle), `DALENGINDEXQQ04` (Dallas Fed Energy Survey, Level of Business Activity — see
below).

## Dallas Fed Energy Survey — a genuine "unique perspective," one sub-index of eight
`DALENGINDEXQQ04` is this project's only energy-sector-specific business-sentiment
index — no equivalent exists anywhere else in the codebase (Eurostat's ESI in Spec 09
Session B is economy-wide, not energy-specific). The Fed's own survey has 8 quarterly
sub-indices (capex, company outlook, employee hours, level of business activity,
number of employees, supplier delivery time, uncertainty, wages/benefits) — only
"Level of Business Activity" is carried here, as the closest analogue to a single
headline figure. Adding any of the other 7 later is the same one-line addition to
`FRED_SERIES`.

## `fredapi` — internals confirmed live, relevant to cassette/secret handling
Reading `fredapi`'s own source (`fred.py`): it builds its request URL with the literal
query param `&api_key=...`, using `urllib` internally (not `requests` — confirmed by
inspecting a recorded cassette's own `User-Agent: Python-urllib/3.12` header) and
requests **XML**, not JSON, from FRED's API (`fredapi` parses the XML itself; this
project's own client never sees it). FRED's raw response body never echoes the
`api_key` back anywhere (checked a real response directly — no `request`/`params`
section like EIA's does). `tests/conftest.py`'s existing `filter_query_parameters:
["api_key", ...]` already covers this exactly — no new filter or
`before_record_response` scrub was needed for FRED's cassettes.

## `fx.usd_{ccy}` naming — deliberately not the spec's own `fx.eurusd` example
Real FX market convention mixes quote direction inconsistently per pair (EURUSD/GBPUSD
quote USD-per-1-foreign-unit; USDTRY quotes TRY-per-1-USD) — replicating that would
need a second per-pair convention table for no real benefit to this project's own
`core/macro.py` (Session B) `to_currency()` use case. `fx.usd_{ccy}` is unambiguous:
`geo={ccy}`, `unit="{ccy} per USD"`, always "how many `{ccy}` you get for 1 USD" — a
plain multiply-to-convert factor, and reads directly off Frankfurter's own `base=USD`
response with no inversion arithmetic. **Don't "fix" this to look like `fx.eurusd`** —
it's a deliberate simplification, not an oversight.

## Frankfurter — real response shape, confirmed live
```json
{"amount": 1, "base": "USD", "start_date": "...", "end_date": "...",
 "rates": {"2026-09-02": {"EUR": 0.86371, "GBP": 0.74167, "TRY": 48.293}, ...}}
```
`rates` is keyed by date, each holding a `{currency: rate}` dict — not a flat
top-level object. Both `api.frankfurter.dev` and `api.frankfurter.app` are live and
return byte-identical data for the same query; this project uses `.dev` per the
spec's own primary listing. A single request covers an arbitrary date range
(`{start}..{end}`) — no per-day looping needed, confirmed live for a multi-year
window. Frankfurter's rates *are* the ECB's own daily reference rate by construction,
so "matches ECB reference" (the spec's own Session A acceptance wording) holds by
definition — there's no separate cross-check step to perform.

## A real historical data point broke a naive test assertion — confirmed live, not a bug
`DCOILWTICO`'s full history (fetched back to 1986 by default — `fredapi` doesn't
truncate) includes the real 2020-04-20 negative WTI print (**-$36.98/bbl**, the
COVID-era storage-capacity crisis). An initial test asserting "every value > 0" failed
against this real data point — fixed by checking only the *latest* value is a
plausible positive price, not the entire history. Worth remembering for any other
energy-price series this pipeline might carry in the future — full-history WTI/Brent
data is not guaranteed to be uniformly positive.

## Eurostat ESI (Session B) — dataset code confirmed, but geo codes were a real trap
Dataset `ei_bssi_m_r2`, `indic=BS-ESI-I` ("Economic sentiment indicator"), `s_adj=SA`
(seasonally adjusted) — all confirmed live. **Bare `EU`/`EA`/`EA19` are not valid geo
codes for this dataset — confirmed live, not assumed**: querying with `geo=EA`
returns a genuinely empty `geo` dimension (`"index":{}`, zero categories) and an empty
`value` object, with **no error at all** — the request succeeds (200) but silently
returns nothing, which would be easy to mistake for "no data available" rather than
"wrong geo code." The real, current codes (Eurostat's own area definitions have been
updated over time) are **`EU27_2020`** (not `EU`) and **`EA20`** (not `EA`/`EA19`);
`DE`/`FR`/`IT`/`ES`/`IE` work directly as ISO2 with no translation.
`eurostat_client.py::GEO_CODES` maps this project's own short codes (`EU`, `DE`, ...)
to Eurostat's real wire codes, so the lake's own `estat.esi.{geo}` series_ids stay
short and don't need the caller to know `EU27_2020` exists at all.

**JSON-stat 2.0's flat-value indexing, confirmed live, not derived from the spec**:
`value` is a dict keyed by a row-major-flattened index string across every
dimension in `payload["id"]` order. This dataset's own query always fixes
`freq`/`indic`/`s_adj` to one category each (size 1), so only `geo` and `time` vary —
confirmed live: `flat_index = geo_position * len(time_dim) + time_position`. A missing
key in `value` is a genuine data gap for that geo/month (not every geo has published
data back to the same start date — confirmed live: EU/DE/IT go back to 1980, IE/FR/ES
have shorter published histories), not a bug to work around.

## `core/macro.py` helpers (Session B)
Four pure transforms, all pd.Series-in/pd.Series-out (no lake I/O) — `deflate`,
`to_currency`, `align_freq`, `year_over_year`, `zscore`. Hand-checked against toy
series with manually-computed expected values (`tests/test_core_macro.py`), per the
spec's own acceptance wording.

**`pd.infer_freq` raises, it doesn't return `None`, for fewer than 3 points —
confirmed live by a failing test on a genuinely realistic 2-point toy series** (a
monthly series with only 2 published months, a real early-history edge case for e.g.
`DALENGINDEXQQ04` or any newly-added series). `align_freq`'s fallback path (deriving a
fixed day-count frequency string from the median index step) needs to be reachable
from a caught `ValueError`, not just a `None` return — the initial implementation only
handled the latter and broke on the former until the test caught it.

**`to_currency`'s `target` parameter is real API-signature parity, not a decoration
that does nothing by mistake** — it isn't used in the actual multiply-by-FX-rate
calculation (the caller already picked the correct single-currency `fx_series` before
calling), kept only because the spec's own text names this exact signature
`to_currency(series, fx_series, target)`. Documented in the function's own docstring
so a future reader doesn't "fix" it into doing redundant validation work.

## Verified (Session B)
A real `EurostatESIClient().get_esi()` call returned 3,152 rows across the 6 tracked
geos (EU/DE/FR/IT/ES/IE), each with plausible current values (EU 98.2, DE 94.1, IT
100.5, etc., as of 2026-08) — confirmed live, not assumed, that different geos have
genuinely different history lengths (EU/DE/IT: 560 months each back to 1980; IE/FR:
500; ES: 473) rather than a uniform start date. A naive test asserting "every ESI
value is in [50, 150]" failed against the *full* history — Italy's real ESI hit 38.4
in 1982 — fixed the same way the FRED WTI test was fixed (Session A): check only the
latest value per geo, not the entire history.

**`core/macro.py`'s helpers were first sanity-checked against real lake data while a
separate, severe bug was silently corrupting that same data** — see `core/CLAUDE.md`
for the full incident. `to_currency(wti, fx_usd_eur, ...)` initially returned the
*exact same number* as the nominal USD input (a real, confirmed-live red flag caught
by actually reading the output rather than assuming a passing test elsewhere meant
the pipeline worked end to end) — traced to `fx.usd_eur` reading back as exactly
`1.0` for every date, a DuckDB-level truncation bug in `core/storage.py` unrelated to
anything in this pipeline. Re-verified after that fix landed:
`to_currency(wti, fx_usd_eur, "EUR")`'s latest value ($71.94) is now genuinely
different from the nominal USD figure ($83.90), as it always should have been.

## Verified (Session A)
A real `pull_macro.py` run wrote all 35 FRED series successfully — 114,534 rows total
(`DGS10` alone: 16,870 daily points back to the 1960s). **Frankfurter genuinely timed
out on that same run** (`ReadTimeout`, real transient flakiness — not GDELT-level
severe, but real) — confirming the per-currency resilience path actually matters here
too, not just in `pipelines/news`: the FRED half of the run still wrote successfully
and printed a clear "no FX rows pulled" rather than crashing the whole script. A
second, standalone call to `pull_fx` succeeded immediately (6,660 rows, EUR/GBP/TRY
back to 2018-01-01, one Frankfurter request per the confirmed date-range support
above). Spot-checked across both FRED groups and FX via `read_ts_long`:
`fred.cpiaucsl` (955 rows, latest 333.x), `fred.dcoilbrenteu` (10,245 rows, latest
~$88/bbl), `fred.dalengindexqq04` (42 rows, latest ~46), `fx.usd_eur`/`fx.usd_try`
(2,220 rows each, latest ~0.86 / ~48) — all real, plausible values.

## Page `10_macro.py` (Session C)
The four visuals from the spec's own visualisation spec: dual-axis broad-dollar-vs-WTI
(`dual_axis_chart`); real-vs-nominal WTI indexed 2018=100 (`core.macro.deflate` +
the new `index_to` helper, plotted as two lines on one shared axis via a plain inline
`go.Figure` — a real *dual-axis* chart would misleadingly imply the two series are on
different scales, when the entire point of indexing both to the same base is to make
them directly comparable on one); energy-in-USD-vs-EUR small multiples (WTI/Brent/
Henry Hub, via `to_currency`); and an ESI heat-strip (`core.theme.category_time_heatmap`,
new — generalises the existing `hour_day_heatmap`'s navy-white-red diverging
colourscale from an hour/day grid to a category/time grid, `zmid` explicit so the
colour centres on 100 regardless of the visible window's own data range).

**Visual 1 uses real FRED data, not a placeholder** — the spec's own text says
"WTI from Spec 07; placeholder until then," anticipating Spec 07 (refinery cracks,
still deferred pending IB Gateway) as the WTI source. Since Spec 10 Session A already
pulls WTI directly from FRED (`fred.dcoilwtico`), there's no placeholder needed at
all — this is real data via a different, already-built source.

**Definition of Done's "at least one other page (01 or 07) using `to_currency` or
`deflate`"**: added to `apps/dashboard/pages/015_us_oil_overview.py` (a sibling of
page 01, since 01 itself carries no price series — only stocks/refining volumes —
and 07 doesn't exist yet) as a single real-WTI-price line, deliberately simpler than
page 10's own dual-line indexed comparison (context for that page's existing
crack-spread caption, not a duplicate of page 10's chart).

## `pull_weekly.py` (Session C)
Same reasoning as `pipelines/news/pull_daily.py`: `pull_macro.py`'s own full-history
pulls are already cheap and idempotent (confirmed live, Session A — well under a
minute per source), so no separate narrower-window entrypoint was needed — this file
exists only so Spec 13 can find a consistently-named weekly entrypoint here.

## Verified (Session C)
All four visuals confirmed live in-browser with real data: dual-axis dollar/WTI,
the real-vs-nominal indexed comparison (the two lines visibly diverge, wider during
high-inflation stretches, as expected), all three USD/EUR small multiples, and the
ESI heat-strip's diverging colours. Page 015's new WTI-real-price section also
confirmed live. No new console errors beyond pre-existing/unrelated dev-server noise.
