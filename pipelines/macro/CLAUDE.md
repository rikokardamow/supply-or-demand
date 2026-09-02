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
