# SPEC 14 — ANALYTICS LAYER (Master File)

**Purpose.** Specs 01–13 ingest raw data. This spec builds the ANALYTICAL layer on top of it:
the metrics, ratios, curve diagnostics, seasonal norms and interpretive heuristics that
professional physical/paper traders use, extracted from the project's trading library
(Bouchouev, Newman, Imsirovic, Carollo, Mack, Wengler, Johnson, Spurga, Yamarone, the EPRI
gas primer, and three academic papers). Every panel here is computable from data the
dashboard already ingests, plus TWO explicitly authorised additions (Section 0.4).

**How this file is used.** Claude Code: read NOTES.md first, then this file, then the
referenced base spec (01–13) for any session you are executing. Work ONE session at a time,
in plan mode, exactly as written. Do not write code until the operator approves the plan.
Each item below carries: INPUTS (existing lake series), FORMULA, CHART, TEST (hand-checked
worked number — these are commands, not suggestions), CAPTION (verbatim on-page text), and
ACCEPTANCE criteria. A plan that omits any TEST number will be rejected.

---

## 0. GLOBAL RULES FOR THIS SPEC

### 0.1 Architecture
- All raw data continues to be written by the existing pipelines to the DuckDB lake in the
  two canonical schemas: `ts_long` (series_id, ts, value, unit, source, revision_date) and
  `flows` (origin, destination, commodity, ts, value, unit, source).
- Derived analytics are computed AT RENDER TIME by pure functions in a new package
  `core/analytics/` reading only from the lake. Pages never call external APIs.
  Exceptions (persisted): (a) the COT pipeline in Session D writes raw positioning data to
  `ts_long` like any other pipeline; (b) regression fits and climatologies that are
  expensive to recompute are cached to `data/cache/analytics/` as parquet with a
  `fitted_through` date column, refreshed by the daily entrypoint when stale > 7 days.
- Every function in `core/analytics/` is pure (DataFrame in → DataFrame/scalar out),
  typed, and unit-tested against the worked numbers in this file. No I/O inside them.

### 0.2 House chart conventions (apply to EVERY panel in this spec)
- Theme: `kardamow` (already defined in Spec 00). Navy `#1a2e4a` primary series,
  light blue `#7fb3d5` secondary. No other series colours without explicit instruction.
- Seasonal panels: x-axis Jan–Dec; 5-year min–max band EXCLUDING 2020 (grey fill,
  20% opacity); current year navy thick (2.5px); prior year light blue thin (1.2px).
  The exclude-2020 rule is absolute for any seasonal statistic in this file.
- Dual-axis charts: primary navy on left axis, secondary light blue on right axis; both
  axes labelled with units; right axis title states the series AND the unit.
- Zero lines and threshold lines: dashed, 1px, annotated with a small text label at the
  right edge (e.g. "carry breakeven", "squeeze zone").
- Titles state the RELATIONSHIP, not the series names. Correct: "Timespreads are pricing
  more storage than tanks report". Wrong: "WTI M1-M2 vs Cushing stocks".
- Every panel renders a caption line (st.caption) with the CAPTION text given below,
  VERBATIM. Captions are part of the acceptance criteria.
- Scatter panels: 5y history as grey points (40% opacity), trailing 13 weeks as red
  points with date labels on the last 4, fit line per item instructions.
- Flow visuals (maps, Sankeys): link/arrow width proportional to volume; colour encodes
  deviation from the 5y same-period seasonal norm — navy within ±1σ, amber (#e67e22)
  above +1σ, light blue below −1σ. Hover shows: level, seasonal norm, % deviation, σ.

Note (this project's own house style, per root `NOTES.md`): the base repo's existing
`core/theme.py` palette is navy `#0f2a4a` / light blue `#5b9bd5`, not the `#1a2e4a` /
`#7fb3d5` this spec names above. Do not introduce a second palette — reuse the existing
`core.theme.NAVY`/`LIGHT_BLUE`/`ORANGE`/`GREY` constants for every rule in this section;
treat this spec's hex values as referring to those same existing constants by role
(primary/secondary), not as new literals to add.

### 0.3 Derived series naming
When a derived value IS persisted (cache or lake), series_id uses prefix `drv.` +
spec + name, e.g. `drv.01.days_cover_crude`, `drv.07.crack_321`. COT raw data uses
prefix `cot.` (it is source data, not derived). Document every id created in the
relevant `pipelines/*/NOTES.md`.

### 0.4 Authorised data additions (the ONLY new external data in this spec)
1. **EIA working storage capacity, Cushing OK** — semi-annual series in the same EIA
   open-data API already used by Spec 01. Resolve the exact series id via the EIA API
   browser at implementation time; NEVER guess ids; record the id in
   `pipelines/eia/NOTES.md`. Needed by items 1.4/1.5/7.32. See §0.8.3 for the confirmed
   report family and the current live figures as of 1 Sept 2026 — the exact facet/series
   ID for the API route still needs a live `/seriesid/` or facet-browser check at
   implementation time; do not assume §0.8's figures are the API's own field names.
2. **CFTC Commitments of Traders, disaggregated, futures+options combined** — free
   public Socrata API at publicreporting.cftc.gov, no key required. Session D only.
   Dataset ID and field names are now CONFIRMED — see §0.8.1, and use those directly
   rather than re-discovering them at implementation time.
   ICE Brent COT: confirmed sourceable from the SAME free CFTC Socrata dataset (ICE
   Futures Europe / ICE Futures Energy Div contracts appear in the disaggregated
   dataset alongside NYMEX contracts — see §0.8.1/§0.8.2) — this REPLACES the original
   plan of scraping ICE's own weekly CSV (which turned out to be paywalled; only ICE's
   PDF-format automated reports are free, and are not worth parsing when the same data
   already exists as structured JSON in the CFTC dataset). Brent positioning is
   therefore no longer a separate-source stretch goal — it is the same pull, filtered
   to a different `cftc_contract_market_code`. Confirm the exact Brent-relevant
   contract code(s) live (§0.8's `111415` is a related refined-product contract, not
   Brent crude itself) before wiring up `cot.bz.*`; if no single clean Brent-crude
   contract code is found within the original 1-hour timebox, descope with a written
   note exactly as before — the sourcing change lowers the bar, it doesn't remove the
   timebox.
Also authorised: additional series ids from APIs ALREADY integrated (EIA weekly import
series in 1.7; FRED ids in Session H; EirGrid fields already pulled by Spec 04).

### 0.5 DO NOT BUILD (out-of-scope — never invent, proxy, or approximate these)
- EU summer–winter gas spread / storage-arb economics → needs a TTF forward curve.
  Not ingested. If TTF futures resolve on IBKR during Spec 07 work, raise it to the
  operator; do not add unilaterally.
- Dark spread / clean spark or dark spreads → needs coal (API2) and EUA carbon prices.
- Brent–Dubai EFS (East–West arb) → needs Dubai swaps (Platts/exchange). On the paid list.
- Freight panels (TC rates, FFA, Baltic indices, WS rates) → needs Baltic/exchange data.
- OPEC spare capacity as a computed series → estimates only; if the MOMR Excel carries a
  spare-capacity table, parse and label it "OPEC secondary-source estimate"; never derive.
- Anything that requires inventing a series id, a price, or a yield that is not in the lake.

### 0.6 Honesty rules
- Items marked EXTENSION below are the operator's/assistant's constructions, not book
  doctrine. Their captions say so. Do not strengthen their claims.
- Where sources disagree (crack ratios: Mack fixed-ratio vs Newman yield-weighted;
  positioning: Newman MM-focus vs Bouchouev MM+OTH-combined; spreads↔inventories
  causality: classic storage reading vs Bouchouev ch.6.2), the caption states the
  disagreement. Never silently pick a side.
- Never weaken a hand-checked test to make code pass. Fix the code.

### 0.7 Session map and dependencies
| Session | Contents | Depends on | Time |
|---|---|---|---|
| 14-A | core/analytics scaffold + M1–M6 curve pull + curve & carry suite (7.29–7.31, 7.36, 7.41, X.53) | Spec 07 A done | weekend 3h |
| 14-B | Spec 01 analytics (1.1–1.8 + flow-map enhancement) | Spec 01 done; 14-A helpers | weekend 3h |
| 14-C | Spec 07 cross panels (7.26 test, 7.27/7.28, 7.32, 7.33, 7.35, 7.37, 7.38) | 14-A, 14-B (1.4) | weekend 3h |
| 14-D | COT pipeline + positioning panels (9.42–9.45) | Spec 00 core | weekend 3h |
| 14-E | Gas analytics: Spec 02 (2.9–2.11) + Spec 03 (3.13–3.14) | Specs 02, 03, 08-A | weekday 1h + weekday 1h |
| 14-F | Power analytics: 4.15, 4.16, 4.18, 4.19, 4.20 | Specs 04, 05, 08-A | weekend 3h |
| 14-G | Supply analytics: 6.21–6.24 | Spec 06 | weekday 1h |
| 14-H | Macro overlays (10.46–10.49) + captions 11.50/11.51 + band-shift monitor X.52 | Specs 10, 11 | weekend 2–3h |

Sessions may be run in any order that respects the "Depends on" column. 14-A first.
Note: this project's own build has, as of this spec being added, completed Specs 00–06
and Spec 08 Session A (weather HDD/CDD only — no ECMWF maps/wind yet); Spec 07 is
deferred pending IB Gateway setup; Specs 09–13 are not yet started. In practice this
means only 14-D (depends only on Spec 00) is runnable now without blocking on other
unfinished specs; 14-A needs Spec 07 Session A; 14-B/14-C need 14-A; 14-E needs Spec 08-A
(done) plus Specs 02/03 (done) so it is also runnable once 14-A/14-B land if an
14-A-independent path is taken for its inputs — check each session's own "Depends on"
column against the real repo state before starting it, don't assume from this table alone.

### 0.8 Data-Source Verification (as of 1 September 2026)
Live-checked against primary sources before this spec was added to the project. Treat the
identifiers/fields below as CONFIRMED and use them directly rather than re-discovering them
at implementation time — this section exists precisely so Session 14-D and the EIA-touching
items don't have to re-derive what's already been verified.

**0.8.1 CFTC Commitments of Traders — Disaggregated Futures-and-Options Combined (Socrata)**
Confirmed live and free.
- Socrata host: `publicreporting.cftc.gov`. Disaggregated Futures-and-Options Combined
  dataset ID: **`kh3c-gbw2`**. JSON: `https://publicreporting.cftc.gov/resource/kh3c-gbw2.json`;
  CSV: `.../kh3c-gbw2.csv`. (For reference, other related datasets: Disaggregated
  Futures-Only `72hh-3qpy`; Legacy Combined `jun7-fc8e`; TFF Futures-Only `98ig-3k9y` —
  this spec uses the Combined dataset only.)
- Confirmed Socrata field names (lower-case, as returned by the API):
  - Managed money: `m_money_positions_long_all`, `m_money_positions_short_all`,
    `m_money_positions_spread_all`
  - Other reportables: `other_rept_positions_long_all`, `other_rept_positions_short_all`,
    `other_rept_positions_spread_all`
  - Producer/merchant: `prod_merc_positions_long_all`, `prod_merc_positions_short_all`
  - Swap dealers: `swap_positions_long_all`, `swap__positions_short_all`,
    `swap__positions_spread_all` (note the double underscore in the two swap short/spread
    fields — confirmed, not a typo in this document)
  - Open interest: `open_interest_all`
  - Report date: `report_date_as_yyyy_mm_dd`; also `yyyy_report_week_ww`
  - Market/contract name: `market_and_exchange_names`, `contract_market_name`
  - CFTC contract market code: `cftc_contract_market_code`; plus `cftc_market_code`,
    `cftc_commodity_code`, `commodity_name`
- **NYMEX WTI contract code — CONFIRMED**: `WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE`,
  `cftc_contract_market_code = '067651'` (contracts of 1,000 barrels). Filter by this code,
  not the name string, for stability. A separate ICE-listed WTI look-alike exists —
  `CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE`, code `067411` — do not confuse the two.
- **ICE Brent is present in this same dataset**: ICE Futures Europe / "ICE Futures Energy
  Div" contracts (e.g. a refined-product contract `GASOLINE CRK-RBOB/BRENT 1st - ICE
  FUTURES ENERGY DIV`, code `111415`, and Brent-linked crude contracts) appear inside the
  CFTC disaggregated dataset — confirm the specific Brent-crude-outright contract code
  live (via `market_and_exchange_names like '%25BRENT%25'` or similar) before wiring up
  `cot.bz.*`; `111415` above is a refined-product spread contract, not Brent crude itself,
  and is shown only to prove ICE contracts generally appear in this dataset.
- Example SoQL query (managed money in WTI for a date range):
  `https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$where=cftc_contract_market_code='067651' AND report_date_as_yyyy_mm_dd between '2025-01-01T00:00:00' and '2026-09-01T00:00:00'&$select=report_date_as_yyyy_mm_dd,contract_market_name,m_money_positions_long_all,m_money_positions_short_all,open_interest_all&$order=report_date_as_yyyy_mm_dd DESC&$limit=5000`
  Filtering by commodity name instead: `$where=market_and_exchange_names like '%25CRUDE OIL, LIGHT SWEET%25'`.
- **No app token required** — CFTC states tokens are not currently issued and the API works
  fine anonymously; Socrata throttles heavily only at very high anonymous volumes. Batch by
  date, `$limit` up to 50,000. **All position/OI fields arrive as strings — cast to
  numeric** (already noted in §0.6/guardrails, reconfirmed live).

**0.8.2 ICE Brent COT direct from ICE Futures Europe — confirmed NOT the right path**
ICE Futures Europe does publish its own weekly COT-style reports for ICE Brent Crude and
ICE Gasoil (modelled on the CFTC long-format disaggregated COT, Fridays 18:30 London for
the Tuesday position), but only as **PDF** files at
`https://www.ice.com/publicdocs/cot_report/automated/` (e.g. `BrentFutOpt_04012022.pdf`) —
free, no login, but not structured data worth parsing. ICE's own structured CSV
end-of-day report packages (via the ICE Report Center) are **subscription/paid**. Since
the same Brent positioning already exists as structured JSON inside the free CFTC dataset
(§0.8.1), source Brent COT from CFTC, not ICE — this is the correction reflected in §0.4.2
and Session D.0 below.

**0.8.3 EIA — Cushing working storage capacity**
The authoritative figure is EIA's semi-annual "Working and Net Available Shell Storage
Capacity" report (published twice yearly — do not expect weekly refresh; forward-fill
between releases per item 1.4). EIA's March 2015 report put Cushing working capacity at
70.8 M bbl; secondary trackers currently cite ~76 M bbl. Current utilisation is low
(~22.4 M bbl ≈ 29.5% of capacity as of 26 Aug 2026 per EIA-sourced reporting; inventories
briefly dipped below 20 M bbl between 19 June and 10 July 2026, prompting an EIA July 2026
review of minimum operating "tank-bottom" levels). These are real, current reference
figures for sanity-checking item 1.4's output — not API field names; still resolve the
exact facet/series ID for this report family live via the EIA API browser as §0.4.1
already instructs, and never hard-code the 70.8/76/22.4 figures above into code.

**0.8.4 EIA API v2 — robustness note (not required, but useful if routes are flaky)**
The v2 `/seriesid/` endpoint accepts legacy v1 dotted IDs directly and auto-translates
them (added Nov 2022, v2.1.0): `https://api.eia.gov/v2/seriesid/PET.WCESTUS1.W?api_key=XXXX`.
This project's existing `pipelines/eia/client.py` already uses the route+facet method
(`frequency=...&data[]=value&facets[series][]=...`) successfully — no change needed there —
but if a NEW series id added by this spec (the storage-capacity report, or any id in item
1.7) doesn't resolve cleanly via route+facet, try `/seriesid/` as a fallback before
concluding the id is wrong; document whichever path actually works in
`pipelines/eia/NOTES.md`, matching this project's own "confirmed live, not guessed"
convention.

**0.8.5 FRED, gridstatus — reconfirms decisions this spec already makes correctly**
`DTWEXBGS` (not the discontinued `DTWEXB`) is confirmed live and is already what
Section H.4 below uses — no change needed. The open-source `gridstatus` library (already
in use since Spec 05, pinned per that spec's own NOTES.md) is confirmed to be the
correct free package — do not confuse with the paid hosted `gridstatusio` product;
Section F.1's ERCOT/PJM inputs should keep using the existing pinned `gridstatus`.

**0.8.6 Not otherwise touching this spec's content**
GPR (Caldara–Iacoviello, item H.1), CME contract conventions (crack/spark heat rates,
item C.1/F.1/F.2), and the general licence posture (CFTC/EIA public domain, FRED
permissive with per-series checks) were all independently reconfirmed live and require no
change to the text below — they're recorded here only so a future session doesn't feel
the need to re-verify them from scratch.

---

## SESSION 14-A — CORE SCAFFOLD, CURVE HISTORY, CARRY SUITE

### A.0 Scaffold
Create `core/analytics/__init__.py` and modules:
`coverage.py`, `curves.py`, `regress.py`, `seasonal_ext.py`, `positioning.py` (stub until
14-D), `power.py` (stub until 14-F). Each module gets a matching test file under
`tests/analytics/`. Add a page `apps/dashboard/pages/14_analytics.py` ONLY if an item
below has no natural home on an existing page; the default is to add panels to the
existing spec pages (curve suite → page 07; coverage → page 01; etc.).

### A.1 Prerequisite — extend futures history to M1–M6 (amends Spec 07 Session A)
- Extend the existing IBKR history module (ib_async, delayed data type 3, the documented
  roll rule — reuse the Spec 07 code path, do not fork it) to pull 2y daily settles for
  CL and BZ months M1..M6 and RB/HO/NG months M1..M2.
- Series ids: `fut.cl.m1`..`fut.cl.m6`, `fut.bz.m1`..`fut.bz.m6`, `fut.rb.m1`,
  `fut.rb.m2`, `fut.ho.m1`, `fut.ho.m2`, `fut.ng.m1`, `fut.ng.m2` → `ts_long`,
  unit `usd_bbl` (RB/HO stored per GALLON as delivered by the exchange, unit `usd_gal`;
  conversion ×42 happens in analytics functions, never at ingest).
- IB I/O stays isolated in the single existing IB module. Graceful-offline behaviour
  from Spec 07 Session C applies unchanged.
- ACCEPTANCE: `read_ts_long(['fut.cl.m3'])` returns ~500 rows; on any given date the
  curve is monotone in expiry ordering of contract months (test the ORDERING logic with
  a fixture, not the market's shape); no ib_insync import anywhere (existing assert).

### A.2 Item 7.29 — Prompt time spreads (the carry signal)
- SOURCE: Bouchouev, *Virtual Barrels*, ch. 5.3.
- INPUTS: `fut.cl.m1`, `fut.cl.m2`, `fut.cl.m6` (and BZ equivalents).
- FORMULA: `spread_12 = F1 − F2` ($/bbl); `spread_16_per_month = (F1 − F6) / 5`.
- FUNCTION: `curves.time_spread(df_wide, near, far, per_month: bool)`.
- CHART (page 07, new "Curve" tab): two lines — M1−M2 navy, (M1−M6)/5 light blue —
  zero line dashed labelled "flat curve". Separate panel per contract (CL, BZ).
- TEST: F1=80.00, F2=79.40 → +0.60 (backwardation). F1=80.00, F6=77.00 →
  (80−77)/5 = **+0.60 /mo**. Assert both to 2 dp.
- CAPTION: "Backwardation pays you to be long (roll yield); contango charges you.
  Hedger behaviour makes this semi-mechanical: contango wide enough to cover storage
  triggers selling, its collapse triggers buying back — see the breakeven band."

### A.3 Item 7.30 — Contango-carry breakeven band
- SOURCE: Bouchouev ch. 2–3 (cost-of-carry floor; no ceiling); Johnson,
  *40 Classic Crude Oil Trades*, floating-storage chapter (the trade in practice).
- INPUTS: `fut.cl.m1`, `fut.cl.m2`; FRED `SOFR` (via the Spec 10 FRED client — if
  Spec 10 is not yet built, hardcode r as a documented constant 0.05 with a TODO and a
  test asserting the constant is replaced once `fred.sofr` exists in the lake).
- CONSTANTS: `U_STORAGE = 0.65` $/bbl/month (Cushing tariff assumption). Document in
  `pipelines/NOTES.md`: "assumption, not data; revisit annually."
- FORMULA: `breakeven = U_STORAGE + F1 × r / 12`; `carry_ratio = −(F1−F2) / breakeven`
  (only meaningful when F1−F2 < 0).
- CHART: M1−M2 navy line; shaded light-blue band from 0 down to −breakeven;
  when the spread trades BELOW the band, shade the gap amber and set a page badge
  "super-contango: carry open".
- TEST: F1=80.00, r=0.05 → financing = 80×0.05/12 = 0.3333; breakeven = 0.65+0.3333 =
  **0.98** $/bbl/mo (2 dp). With M1−M2 = −1.20: carry_ratio = 1.20/0.98 = **1.22** →
  flag "carry open". Assert both.
- CAPTION: "Contango deeper than the band means storage earns riskless carry — expect
  tanks to fill and the spread to stabilise; the floor steepens as cheap storage
  saturates (floating storage is the expensive last tier). There is no symmetric
  ceiling: backwardation can run (Bouchouev ch. 2)."

### A.4 Item 7.31 — Curve convexity regime
- SOURCE: Bouchouev ch. 6.1.
- INPUTS: `fut.cl.m1..m3`.
- FORMULA: `cv = F1 − 2·F2 + F3`. Regime = (sign of F1−F2: backwardated/contangoed) ×
  (sign of cv: convex/concave) → four labels.
- CHART: cv line with zero dashed; below it a 2×2 occupancy table (% of trailing 252
  trading days in each regime).
- TEST: F1=78.0, F2=79.0, F3=79.6 → 78 − 158 + 79.6 = **−0.40** → label
  "contangoed-concave". Assert value 2 dp and label string.
- CAPTION: "A concave front (prompt spread rich vs the next spread) has historically
  rolled down — hedger supply concentrates at the front. Convex fronts carry squeeze
  risk. A regime flag, not a trade instruction."

### A.5 Item 7.36 — Roll yield panel
- SOURCE: Bouchouev ch. 4.
- FORMULA: `roll_ann = (F1 − F2) / F2 × 12` (fraction; display %). CL and BZ.
- CHART: two lines, zero dashed.
- TEST: F1=80, F2=79 → 1/79×12 = 0.151899 → **15.19%** (2 dp).
- CAPTION: "In backwardation, length pays you to wait; in contango it bleeds. Much of
  the long-run futures P&L is this term, not price direction — which is why curve
  shape, not price, drives allocator flows."

### A.6 Item X.53 — Implied convenience yield
- SOURCE: Bouchouev ch. 2 (Kaldor).
- FORMULA: `cy = (F1 − F2) + F1 × r/12 + U_STORAGE` ($/bbl/month).
- CHART: line, zero dashed, on the Curve tab beneath 7.29.
- TEST: F1−F2 = +1.00, F1=80, r=0.05, U=0.65 → 1.00 + 0.3333 + 0.65 = **1.98** (2 dp).
- CAPTION: "The price of immediacy. High convenience yield = the physical market values
  barrels-in-hand — tightness — even when flat price is unremarkable. Same information
  as the time spread restated in cost-of-carry units; plot both, trade neither blindly."

### A.7 Item 7.41 — Boundary-event annotation (static, no computation)
Add a dismissible st.info on the Curve tab: "20 Apr 2020: WTI M1 settled −$37.63.
Extrapolated inventories breached Cushing capacity in expectation while TAS mechanics
concentrated forced selling (Bouchouev ch. 3.5; Imsirovic ch. 13). Spreads near storage
boundaries are not mean-reverting."

### 14-A ACCEPTANCE (operator verifies)
- `uv run pytest tests/analytics/test_curves.py` green with tests 7.29/7.30/7.31/7.36/X.53.
- Page 07 Curve tab renders offline from the lake with all five panels + annotation.
- `git grep ib_insync` empty; no API call originates from any page module.

---

## SESSION 14-B — SPEC 01 ANALYTICS (US PADD / WPSR)

### B.1 Item 1.1 — Days of forward cover
- SOURCE: Carollo, *Understanding Oil Prices*, ch. 6; Yamarone, *Trader's Guide*, ch. 7.
- INPUTS (all already pulled by Spec 01): commercial crude stocks (WCESTUS1); refinery
  net crude runs; gasoline stocks; distillate stocks; 4-wk avg product supplied per fuel.
- FORMULA: `days_cover = stock_kb / demand_kbd`. Crude uses refinery runs as the
  demand rate; products use their own 4-wk product supplied.
- FUNCTION: `coverage.days_of_cover(stock: Series, rate: Series) -> Series` (aligns
  indexes, forward-fills the slower series ≤ 7 days, else NaN).
- CHART: three seasonal panels (crude / gasoline / distillate cover), house band rules.
- TEST: 420,000 kb ÷ 16,000 kbd = **26.25 days**; 220,000 kb ÷ 9,000 kbd = **24.44 days**
  (2 dp each).
- CAPTION: "Days of cover, not barrels, is the tightness metric: a 'record low' stock
  level with low runs may be comfortable, and a normal level with record runs may be
  tight. Read the band position, not the level."

### B.2 Item 1.2 — Stock-change vs price-change scatter
- SOURCE: Carollo ch. 2 (Fig 2.5) and ch. 6 (Fig 6.1).
- INPUTS: weekly Δ total US commercial crude stocks (mb); `fut.cl.m1` weekly % change
  (Wed-to-Wed to align with WPSR weeks).
- CHART: scatter per house rules; OLS fit navy with R² annotated bottom-right.
- TEST: sign test only — assert fitted slope < 0 on the 5y window of REAL lake data is
  NOT a unit test (market-dependent); instead unit-test the alignment logic with a
  synthetic fixture where y = −0.5x + noise and assert slope ∈ (−0.7, −0.3).
- CAPTION: "The fit is real but weak: inventory data explains a minority of weekly price
  variance. When red points sit far off the line, flows and positioning, not barrels,
  are driving price — check the COT panel."

### B.3 Item 1.3 — WPSR adjustment line as data-quality tell
- SOURCE: grounded in Carollo ch. 6 Box 6.1; weekly-adjustment application is EXTENSION.
- INPUTS: EIA weekly crude "adjustment" series (in the WPSR API family; resolve the id
  via the API browser, document it). §0.8's `WCRAUUS2` is high-probability but
  unverified — confirm with one `/seriesid/` call before relying on it.
- FORMULA: `adjustment_mb = adj_kbd × 7 / 1000`;
  `residual_share = min(|adjustment_mb| / max(|Δcrude_stocks_mb|, 0.1), 2.0)`.
- CHART: 4-wk avg adjustment as navy bars (kbd, left axis); residual_share light-blue
  line (right axis, 0–2); dashed threshold at 0.5 labelled "artefact zone".
- TEST: adj = +300 kbd → 300×7/1000 = **2.1 mb**; with headline build 2.1 mb →
  residual_share = **1.00** exactly.
- CAPTION: "When the adjustment explains most of the headline change, the draw/build is
  a statistical artefact. Discount WPSR-driven price reactions in weeks where the
  residual share exceeds 0.5, and expect revisions."

### B.4 Item 1.4 — Cushing capacity utilisation
- SOURCE: Bouchouev ch. 3 and ch. 6.2 (utilisation, not barrels, is the metric).
- INPUTS: Cushing crude stocks (Spec 01); NEW: EIA Cushing working storage capacity
  (Section 0.4 addition; semi-annual; forward-fill between releases). See §0.8.3 for
  the current live reference figures to sanity-check against (do not hard-code them).
- FORMULA: `util = stock / working_capacity`.
- CHART: utilisation % line; dashed reference lines at 20% ("squeeze zone") and 80%
  ("congestion zone").
- TEST: 38,000 ÷ 78,000 = **48.7%** (1 dp).
- CAPTION: "Below ~20% the market prices squeeze risk and spreads can gap into
  backwardation; above ~80% carry steepens as marginal storage gets expensive. Between
  the zones utilisation is weak as a signal — see the causality caveat on the spreads
  page."

### B.5 Item 1.5 — Weeks-to-boundary extrapolation
- SOURCE: Bouchouev ch. 3.5. 
- FORMULA: trailing 4-wk mean Δstock. If > 0: `weeks_to_top = (capacity − stock)/build`;
  if < 0: `weeks_to_floor = (stock − 0.2×capacity)/draw`; else None.
- CHART: KPI metric beside the utilisation chart; amber when < 8 weeks.
- TEST: capacity 78, stock 60, build 3 mb/wk → (78−60)/3 = **6.0 weeks** (1 dp).
- CAPTION: "A boundary cannot be breached — flows must adjust first. A short runway does
  not predict the breach; it predicts violent spread behaviour as the market forces the
  adjustment (Cushing, April 2020)."

### B.6 Item 1.6 — Utilisation vs margin lead–lag
- SOURCE: Carollo ch. 11, Figs 11.3–11.5.
- INPUTS: Spec 01 refinery utilisation; `drv.07.crack_321` (or compute inline from
  futures until 14-C lands).
- BUILD: on the existing Spec 07 dual-axis chart add a lag toggle (0/4/8 weeks shifting
  the crack forward) and print the max-cross-correlation lag (0..12 wk grid) in the
  caption. Function `regress.best_lag(x, y, max_lag)`.
- TEST: synthetic y(t) = x(t−4) → `best_lag` returns **4**.
- CAPTION: "Cracks lead runs by roughly one to two months: strong margins today are next
  month's crude demand and the month after's product supply. A margin collapse with
  utilisation still high means product builds are coming."

### B.7 Item 1.7 — Gasoline imports: finished vs blending components
- SOURCE: Carollo ch. 11, Fig 11.6.
- INPUTS: NEW series ids from the EXISTING EIA API: PADD1 weekly imports of finished
  motor gasoline and of gasoline blending components. §0.8's live-confirmed ids:
  finished motor gasoline `W_EPM0F_IM0_R10-Z00_MBBLD`; blending components
  `WBCIM_R10-Z00_2` — verify these still resolve at implementation time (per this
  project's own "don't guess schemas" rule) before hard-coding them into the pull.
- CHART: stacked area, navy = blending components, light blue = finished, 4-wk avg;
  seasonal band on the total.
- TEST: 550 + 250 = **800 kbd**; assert stack total equals the summed series within
  float tolerance on a fixture.
- CAPTION: "A rising blendstock share signals the US is short octane/blending capacity
  rather than short finished gasoline — bullish RBOB cracks relative to European
  gasoline; the transatlantic arb is doing the balancing."

### B.8 Item 1.8 — Product supplied YoY (demand line)
- SOURCE: Spurga, *Commodity Fundamentals*, energy chapters; Yamarone's YoY discipline.
- FORMULA: 4-wk avg product supplied, YoY % = (this/last − 1) × 100, per product
  (gasoline, distillate, jet, total).
- CHART: small multiples, zero dashed.
- TEST: 9,100 vs 8,750 → **+4.0%** (1 dp).
- CAPTION: "Weekly product supplied is noise; the 4-week YoY is the signal. Divergence
  between products dates the cycle: distillate follows freight/industry, gasoline the
  consumer, jet reopening/travel."

### B.9 PADD flow-map enhancement (amends Spec 01 Session B map)
- Colour every inter-PADD arrow by deviation from that corridor's 5y same-month norm
  (ex-2020) using the Section 0.2 flow-colour rule, computed by a new
  `seasonal_ext.flow_deviation(flows_df)` helper; add "net balance in days of PADD
  cover" to each PADD hover, reusing B.1's function with PADD-level runs.
- TEST: corridor flow equal to its norm → σ-deviation 0 → colour class "navy".
- ACCEPTANCE: map still renders offline; hover shows level / norm / %dev / σ.

### 14-B ACCEPTANCE
- All tests above green; page 01 gains a "Coverage & balance-quality" tab with panels
  B.1–B.5, B.7, B.8; B.6 modifies the Spec 07 dual-axis; B.9 modifies the map.
- Cross-check ONE number: latest crude days-of-cover recomputed by hand from the two
  EIA browser values matches the dashboard KPI to 0.1 days.

---

## SESSION 14-C — SPEC 07 CROSS PANELS (CRACKS, RATIOS, ACCORDION)

### C.1 Item 7.26 — Second hand-checked 3-2-1 case (test only)
- SOURCE: Mack, *Energy Trading and Risk Management*, ch. 4.6.1 worked table.
- Add to `tests/test_cracks.py` (beside the existing $25.60 case): crude $25.00/bbl,
  gasoline $0.80/gal, heating oil $0.70/gal → gasoline 0.80×42 = 33.60/bbl, ×2 = 67.20;
  HO 0.70×42 = 29.40; products 96.60 − crude 75.00 = 21.60; ÷3 = **$7.20/bbl** (2 dp).
- Add caption to the existing crack panel: "A gross margin, not profit: opex,
  natural-gas cost and RINs sit between this line and a refiner's P&L. Its level
  matters less than its position in the seasonal band."

### C.2 Items 7.27 + 7.28 — Yield-weighted GRM (two-product honest version) + ratio note
- SOURCE: Newman, *World of Oil Derivatives*, ch. 2 (yield-weighted margins); Mack
  ch. 6.5 Table 6.6 (fixed-ratio conventions). Books disagree — caption carries both.
- FORMULA: `grm2 = 0.60 × rb_usd_bbl + 0.40 × ho_usd_bbl − cl` where rb/ho per-bbl =
  per-gal × 42. Weights are a stylised light-sweet US yield collapsed onto two
  products; document as constants with that sentence.
- CHART: grm2 line beside the 3-2-1 on page 07.
- TEST: RB $100/bbl, HO $110/bbl, CL $80 → 60.00 + 44.00 − 80.00 = **$24.00** exactly.
- CAPTION: "3-2-1 is a US-convention proxy (Mack); Newman argues real margins are
  yield-weighted and refinery-specific. This two-product version omits jet, naphtha
  and resid by construction — use its changes and its divergence from the 3-2-1, not
  its level, and never quote it as a refinery margin."

### C.3 Item 7.32 — Time-spread vs inventory scatter, with the causality caveat
- SOURCE: Bouchouev ch. 6.2 (inventories do NOT predict spreads; the arrow runs
  spreads → future inventories) vs the classic theory-of-storage reading (his ch. 3).
  Disagreement is the point of the caption.
- INPUTS: Cushing utilisation (B.4) weekly; `fut.cl.m1 − fut.cl.m2` same-week.
- CHART: scatter per house rules; fit ONLY on the 20–80% utilisation interior, dashed;
  no fit through the boundary regions.
- TEST: interior-fit routine on a synthetic set with negative interior slope returns
  slope < 0 and excludes points outside [0.2, 0.8].
- CAPTION: "Levels and spreads move together today, but inventory levels have little
  power to predict tomorrow's spreads — causality mostly runs spreads → future
  inventories, because storage decisions are made off the curve (Bouchouev ch. 6.2).
  The scatter earns its keep at the boundaries: below ~20% utilisation squeeze risk is
  asymmetric; near tank-tops the boundary forces the flow."

### C.4 Item 7.33 — WTI–Brent accordion
- SOURCE: Bouchouev ch. 6.3 (signal, one-leg month shift, three regimes); Imsirovic,
  *Trading and Price Discovery*, ch. 13.
- FORMULA: `s = bz_m2 − cl_m1` (Brent leg shifted one month for shipping time, per
  Bouchouev's practitioner note); `dev = s − MA60(s)`; `eps = 1.5 × rolling_std60(dev)`;
  `z = dev / rolling_std60(dev)`.
- CHART: dev navy line, ±eps light-blue band; background shading with labels for the
  three regimes — "US import era (pre-2011)", "bottleneck era (2011–2015)",
  "interconnected (post-2015)" — applied only where the 2y data window overlaps.
- TEST: s = −4.20, MA60 = −3.40 → dev = **−0.80**; std = 0.50 → z = **−1.60** →
  outside band → flag "stretched". Assert 2 dp + flag.
- CAPTION: "Post-2015, physical export arbitrage caps deviations near shipping cost, so
  stretches mean-revert — unless freight has spiked or infrastructure broke; the band
  proxies freight uncertainty, it doesn't measure it. In a bottleneck regime this chart
  is a trap: check the regime label first (Bouchouev's discretionary overlay — knowing
  when not to trade the signal)."

### C.5 Item 7.35 — Crack spread as a leading indicator of crude
- SOURCE: Murat & Tokat (2009), Energy Economics (in the project library): post-2003
  structural break; unidirectional causality crack-futures → spot crude; forecasting
  power ≈ crude futures.
- INPUTS: 3-2-1 crack series; `fut.cl.m1`.
- CHART: (a) scatter — x = 8-wk Δcrack, y = SUBSEQUENT 4-wk ΔCL, house scatter rules,
  dashed fit; (b) small line — 2y rolling correlation of lagged Δcrack with ΔCL.
- TEST: mechanics only — rolling-correlation series has no NaN after the warm-up
  window on a fixture. Do NOT hard-code the sign: the paper's own finding is
  regime-dependent (structural break).
- CAPTION: "Refiners are the marginal crude buyer; their margin is their bid. Widening
  cracks with flat crude have historically pulled crude up (Murat & Tokat 2009). Treat
  as a tilt, not a timing tool — the relationship is regime-dependent by the paper's
  own structural-break finding."

### C.6 Item 7.37 — Product/crude ratios, seasonal
- SOURCE: Carollo ch. 11, Figs 11.12–11.13; Spurga (seasonal demand rotation).
- FORMULA: `rb_ratio = (rb_usd_gal × 42) / bz_m1`; `ho_ratio = (ho_usd_gal × 42) / bz_m1`.
- CHART: two seasonal panels, house band rules, unitless axis.
- TEST: RB $2.40/gal → 100.80/bbl; BZ $84.00 → **1.200** (3 dp).
- CAPTION: "The ratios rotate leadership: gasoline into driving season, heating oil into
  winter. A ratio breaking its band out of season is a supply event (refinery outages,
  spec changes), not demand — cross-check the events overlay."

### C.7 Item 7.38 — Realized volatility panel
- SOURCE: Wengler, *Managing Energy Risk*, ch. 6; Carollo ch. 2 Fig 2.8.
- FORMULA: `rv = std(log_returns, 20d) × sqrt(252)`, per contract (CL, BZ, RB, HO, NG).
- CHART: five lines (CL navy, BZ light blue, others thin grey with legend).
- TEST: constant daily σ = 2% → 0.02 × 15.8745 = 0.31749 → **31.75%** (1 dp on %).
- CAPTION: "Oil vol clusters and spikes with regime breaks in either direction; NG vol
  is seasonal by construction. Rising vol with an unchanged price level often precedes
  the move — it measures disagreement."

### 14-C ACCEPTANCE
- All tests green including BOTH crack hand-checks (25.60 and 7.20) and the GRM 24.00.
- Page 07 gains: GRM line, ratio seasonals, accordion panel, crack-lead panel, RV panel,
  spread-vs-inventory scatter; every panel carries its verbatim caption.

---

## SESSION 14-D — COT PIPELINE + POSITIONING PANELS (new mini-pipeline)

### D.0 Pipeline `pipelines/cftc/`
- SOURCE for interpretation: Newman ch. 3 (category anatomy; T−3 Tuesday data released
  Friday); Bouchouev ch. 6.5 (merge MM + Other Reportables; MM alone misleads).
- Data: CFTC Public Reporting API (Socrata, publicreporting.cftc.gov), disaggregated
  futures-and-options-combined dataset, **id `kh3c-gbw2`** (confirmed live — see §0.8.1
  for the full field-name list and a worked SoQL query; use these directly). No key.
  Respect polite rate limits; vcr cassettes for tests; the cassette secret-scan
  meta-test from Spec 13 applies (no tokens exist here, but the scan still runs).
- Contract: NYMEX WTI (CME), `cftc_contract_market_code = '067651'` — mandatory.
  ICE Brent COT — no longer a separate-source stretch: it is confirmed available in
  this SAME dataset (§0.8.1/§0.8.2 — ICE's own CSV packages are paywalled, only free as
  unstructured PDF, so don't use ICE directly). Find the exact Brent-crude-outright
  `cftc_contract_market_code` live (query `market_and_exchange_names` for Brent/ICE
  crude, not the `111415` refined-product example in §0.8.1) within a 1-hour timebox;
  if no single clean code is found in that time, descope Brent positioning with a
  written note in this file and proceed with WTI only, exactly as originally planned —
  only the SOURCE changed (CFTC instead of ICE), not the timebox or the descope option.
- Write to `ts_long`, weekly rows dated the TUESDAY of the report (`ts` = Tuesday), with
  a second field convention: also store `release_lag_days = 3` in
  `pipelines/cftc/NOTES.md` documentation (not in the lake).
- Series ids (contracts, longs minus shorts): `cot.cl.mm_net`, `cot.cl.oth_net`,
  `cot.cl.nc_net` (= mm_net + oth_net), `cot.cl.oi` (total open interest);
  Brent equivalents `cot.bz.*` if the (now CFTC-sourced) stretch lands.
- Idempotency: re-running the pull must not duplicate weeks (test: run twice on
  cassette, row count unchanged).
- All position/OI fields arrive from Socrata as strings — cast to numeric before writing
  to `ts_long` (confirmed live, §0.8.1 — do not assume numeric JSON types).

### D.1 Item 9.42 — Positioning dashboard
- FORMULA: mb-equivalent = contracts × 1,000 / 1e6 → display in mb:
  `nc_net_mb = nc_net_contracts × 1000 / 1_000_000` (i.e. contracts ÷ 1000 → mb...
  verify: 1 contract = 1,000 bbl; 250,000 contracts × 1,000 bbl = 250,000,000 bbl =
  **250 mb**). Percentile bands: rolling 5y 20th/80th percentiles of nc_net_mb.
- CHART: nc_net_mb navy line; 20/80 percentile band light-blue shade; MM and OTH as
  thin toggleable lines (grey).
- TEST: 250,000 contracts → **250 mb** exactly.
- CAPTION: "Positioning is a conditioner, not a signal: extremes (outside the 20/80
  band) make the market fragile to news in the crowded direction. Newman reads Managed
  Money as the fast-money gauge; Bouchouev shows Other Reportables hides comparable
  non-registered money — the headline here is the sum. Data is Tuesday's picture
  released Friday — never read it as current."

### D.2 Item 9.43 — Speculative-fragility flag
- SOURCE: Newman ch. 3 (GasNap 2022 stop-out case).
- FORMULA: flag TRUE when ALL of: |nc_net| beyond its 10th/90th 5y percentile
  (direction-aware); `cot.cl.oi` above its 90th 5y percentile; trailing 4-wk price move
  of the SAME contract has sign OPPOSITE to nc_net's sign.
- RENDER: amber badge on the page-07 flat-price header when TRUE, text
  "positioning fragile: crowded {long|short} fighting the tape".
- TEST (synthetic): nc_net at 2nd pctile (extreme short), oi at 95th pctile, price
  +6% over 4 wks → **TRUE**. Any one condition removed → FALSE.
- CAPTION: "When crowded positioning fights the tape, stop-outs — not fundamentals —
  write the next chapter. The flag marks fragility and the likely violence of moves,
  not their direction's rightness."

### D.3 Item 9.44 — Positioning-momentum signal
- SOURCE: Bouchouev ch. 6.5 (πNC; parameters deliberately unoptimised; encode the lag).
- FORMULA: `signal = sign(MA(nc_net, 4wk) − MA(nc_net, 13wk))`, evaluated only on data
  available as of each Friday (shift the Tuesday-dated series +3 days before any
  comparison with prices).
- CHART: ±1 step line beneath D.1.
- TEST: monotonically rising synthetic nc_net → signal **+1** after warm-up; assert the
  3-day availability shift is applied (a value dated Tue appears in the signal series
  no earlier than that week's Friday).
- CAPTION: "Follows the flow of financial money with the reporting lag built in.
  Bouchouev declines to optimise the windows — so does this panel; 4/13 is a
  convention, not a claim."

### D.4 Item 9.45 — Event-to-flow hover discipline (caption enhancement, Spec 09 pages)
- Extend each event-marker hover template with the line:
  "headline → who must trade → in which contract → against what liquidity?"
- SOURCE: Newman ch. 3, OPEC-cut April-2023 walk-through. No computation.

### 14-D ACCEPTANCE
- Pipeline idempotent on cassette; tests D.1–D.3 green; no NewsAPI-style ToS issue
  (CFTC data is public-domain US government data — note this in the licences file).
- Cross-check ONE number: latest WTI MM net long on the CFTC site matches `cot.cl.mm_net`.

---

## SESSION 14-E — GAS ANALYTICS (SPECS 02 + 03)

### E.1 Item 2.9 — Days of winter cover (EU gas)
- SOURCE: *Understanding Natural Gas Markets* primer, storage/demand section.
- INPUTS: AGSI+ EU gasInStorage (TWh); historical daily net withdrawal (Spec 02).
- FORMULA: `winter_rate` = mean daily NET withdrawal over Nov 1–Mar 31 of the 5 prior
  gas-years ex-2020 (winter 2020/21 counts as affected → exclude);
  `days_cover = gas_in_storage / winter_rate`.
- CHART: KPI + line of days_cover with seasonal band.
- TEST: 800 TWh ÷ 4.0 TWh/d = **200 days** (integer).
- CAPTION: "Cover above ~150 days entering November is comfortable; the metric matters
  most in February, when a cold snap meets a depleted denominator. Read jointly with
  the HDD forecast panel."

### E.2 Item 2.10 — Fill trajectory vs 1 Nov target (EXTENSION framing)
- FORMULA: `pace_14d` = mean daily Δfill_pct over trailing 14 days;
  `projected = min(fill_pct + pace_14d × days_to_nov1, 100)`; on-target iff ≥ 90.
- CHART: on the existing worm chart add a dashed navy projection segment from today to
  1 Nov and a marker at (Nov 1, 90%).
- TEST: Aug 1, fill 78.0, pace +0.15 pp/d, 92 days → 78.0 + 13.8 = **91.8%** → flag
  "on target".
- CAPTION: "The projection is naïve by design — it assumes today's pace persists. A
  projection below target is the market's problem to solve via price; watch the
  injection pace respond. (EU-target framing is this dashboard's extension of the
  primer's adequacy logic, not book doctrine.)"

### E.3 Item 2.11 — Weather-adjusted storage surprise (needs Spec 08-A)
- SOURCE: primer (weather dominance); regression construction is EXTENSION.
- FORMULA: OLS on 3y trailing daily data: `Δfill_pp ~ α + β·HDD_EU_popweighted`;
  `surprise = actual − fitted`; display 7-day rolling sum. Cache the fit per §0.1.
- CHART: bar chart of 7d-summed surprise, navy, zero dashed.
- TEST (synthetic): α=+0.10, β=−0.02; HDD=10 → fitted −0.10; actual −0.30 →
  surprise **−0.20 pp** (2 dp).
- CAPTION: "A negative surprise means storage drew harder than the weather warranted —
  LNG shortfall, industrial restart, or export pull. Persistent surprises, not single
  days, carry signal."

### E.4 Item 3.13 — Corridor flow vs seasonal norm + capacity utilisation
- SOURCE: primer transmission section; corridor framing EXTENSION.
- INPUTS: Spec 03 daily corridor flows; technical capacity from the cached
  operator-point directory (fields exist in the directory Spec 03-A builds).
- FORMULA: `util = flow / technical_capacity`;
  `dev_sigma = (flow − norm) / sd` where norm/sd = 5y same-ISO-week mean/sd ex-2020.
- CHART: existing small-multiples gain a caption row "util X% · dev ±Y σ"; Sankey links
  and map arrows recoloured by dev_sigma per §0.2.
- TEST: flow 330 mcm/d, capacity 360 → **91.7%**; norm 320, sd 10 → **+1.0σ**.
- CAPTION: "High utilisation with positive deviation means the corridor is maxed and
  cannot respond to more demand — price, not flow, must adjust. Negative deviation at
  low utilisation is a demand signal, not a supply one."

### E.5 Item 3.14 — Nomination-gap reading rule (caption only, on the Spec 03-D panel)
- CAPTION (verbatim, marked as extension of Newman's flow logic): "One-day gaps are
  operational noise. Realised persistently below nominated across ≥3 gas-days on one
  corridor is a physical statement — maintenance, upstream shortfall, or commercial
  withholding — and usually precedes the headline."

### 14-E ACCEPTANCE — tests E.1–E.4 green; EU fill %, days-cover and one corridor's
util % cross-checked against agsi.gie.eu and transparency.entsog.eu respectively.

---

## SESSION 14-F — POWER ANALYTICS (SPECS 04 + 05)

### F.1 Item 4.15 — Spark spread (US)
- SOURCE: Mack ch. 4.6.2 and ch. 6.6 (definitions, conventions, worked case).
- INPUTS: ERCOT and PJM daily average LMP (gridstatus, Spec 05); Henry Hub daily spot
  (EIA, Spec 05). EU spark: DO NOT BUILD (no TTF — §0.5).
- FORMULA: `spark = lmp − gas × HR/1000`, HR in Btu/kWh; compute at HR = 7,500
  ("efficient CCGT") and 10,000 ("market convention") — Mack's tiers.
- CHART: two lines per ISO (7,500 navy, 10,000 light blue), zero dashed.
- TEST (Mack's case): LMP $25/MWh, gas $2.00/MMBtu, HR 10,000 → 25 − 20 = **$5.00/MWh**
  exactly.
- CAPTION: "Positive spark at 7,500 but negative at 10,000 means only efficient units
  clear — the fleet margin is thin. Sustained negative spark at 7,500 with high load
  means another fuel or scarcity pricing is setting the margin."

Note: this project's Spec 05 only ingests CAISO and NYISO (ERCOT/PJM were confirmed
unusable and swapped out during Spec 05 Session B — see `pipelines/gridstatus_iso/NOTES.md`).
Adapt F.1/F.2 to CAISO/NYISO's own Henry-Hub-vs-LMP pairing, or revisit ERCOT/PJM
ingestion first — do not silently substitute a different ISO's data without flagging
the change here.

### F.2 Item 4.16 — Implied market heat rate
- SOURCE: Mack ch. 4.6.2 (tiers 7,500 / 10,000 / 15,000).
- FORMULA: `ihr = lmp / gas × 1000` (Btu/kWh).
- CHART: line per ISO with dashed reference lines at the three tiers, labelled
  "efficient / average / inefficient (Mack)".
- TEST: LMP 40, gas 2.5 → **16,000** exactly.
- CAPTION: "Implied heat rate above ~15,000 means the price isn't about fuel any more —
  scarcity, transmission, or weather is in charge. Below 7,500, gas is being priced out
  by renewables or cheap baseload."

### F.3 Item 4.18 — Gas share of generation vs gas price
- SOURCE: primer, demand section (coal–gas dispatch competition). Coal-price leg is
  OUT OF SCOPE; this version needs no coal price.
- INPUTS: monthly gas share of ISO generation (Spec 05 mix); monthly avg Henry Hub.
- CHART: scatter, 5y grey, current month red; piecewise-linear or LOWESS fit navy.
- TEST: fit routine on synthetic negative-slope data returns negative average slope
  (mechanics test; do not hard-code market values).
- CAPTION: "The curve's steep region is the switching band: small gas-price moves swing
  large volumes of gas demand. When the current point sits off the historical curve,
  coal retirements or renewables have shifted the band — recalibrate priors, not the
  data."

### F.4 Item 4.19 — Temperature-normalised load (needs Spec 08-A)
- SOURCE: primer (weather dominance) + Wengler ch. 6 (seasonality is structural and it
  shifts).
- FORMULA: per zone/ISO, OLS on 3y daily: `load ~ α + β1·HDD + β2·CDD + weekday
  dummies`; residual = actual − fitted; display 28-day mean residual. Cache fits.
- CHART: residual line, zero dashed, per zone (DE_LU, FR, IE + ERCOT, PJM).
- TEST (synthetic): α=50, β2=0.8 GW/CDD, weekday effect 0; CDD=10 → fitted 58;
  actual 60 → residual **+2.0 GW** (1 dp).
- CAPTION: "Weather explains most load variance; the residual is the economy. A
  drifting residual is an industrial-activity signal weeks ahead of official
  statistics."

Note: this project's Spec 08 Session A already builds NYC/LA CDD-anomaly-vs-ISO-load
dual-axis charts against NYISO/CAISO (not ERCOT/PJM, per the F.1 note above) — reuse
that existing weather-join pattern (`pipelines/weather/` + `apps/dashboard/pages/
08_weather.py`) rather than re-deriving HDD/CDD joins from scratch.

### F.5 Item 4.20 — SNSP vs price (Ireland panel)
- SOURCE: Palgrave Handbook of International Energy Economics (978-3-030-86884-0),
  power chapters; Newman ch. 8 on storage-less power. Binned-curve construction is
  EXTENSION.
- INPUTS: EirGrid SNSP (Spec 04-C); IE_SEM day-ahead price (Spec 04-A).
- FORMULA: bin hourly SNSP into deciles; per bin compute mean and IQR of DA price.
- CHART: navy line of bin means with light-blue IQR band, x = SNSP decile midpoints.
- TEST: on the real joined sample assert mean(price | top decile) <
  mean(price | bottom decile) — if the assertion fails on live data, DO NOT weaken it;
  flag to the operator (it would itself be a finding).
- CAPTION: "The steepness of this curve is the cannibalisation rate. It flattens as
  interconnection and storage grow — track the curve's shape year over year, not the
  points."

### 14-F ACCEPTANCE — tests green; ERCOT spark cross-checked by hand from one day's
LMP and Henry Hub print (or CAISO/NYISO equivalent per the F.1 note); Ireland panel
renders on page 04.

---

## SESSION 14-G — SUPPLY ANALYTICS (SPEC 06)

### G.1 Item 6.21 — OPEC production vs Brent overlay
- SOURCE: Carollo ch. 1, Fig 1.2.
- INPUTS: MOMR secondary-source OPEC crude output (Spec 06); `fut.bz.m1`;
  Spec 09 OPEC-tagged events.
- CHART: dual-axis (output navy mb/d LHS; Brent light blue RHS) with event markers
  on-chart per house style.
- TEST: series-alignment only (both non-empty on shared monthly index in fixture).
- CAPTION: "Cuts into weak demand defend price at the cost of share; cuts that hold
  while inventories draw are the bullish configuration. Output rising alongside price
  means demand, not OPEC, is in charge."

### G.2 Item 6.22 — Call on OPEC
- SOURCE: Carollo ch. 6 (classic balance model — used WITH his scepticism, see G.3).
- INPUTS: MOMR Excel: world demand, non-OPEC supply, OPEC NGLs, OPEC crude output —
  all parsed by Spec 06-A with vintages.
- FORMULA: `call = world_demand − non_opec_supply − opec_ngls`;
  `implied_balance = opec_crude_output − call` (positive = implied global build).
- CHART: monthly bars of implied_balance (navy), vintage selector reusing the Spec 06
  revision machinery.
- TEST: demand 104.0, non-OPEC 71.5, NGLs 5.5 → call **27.0**; output 26.5 →
  implied **−0.5 mb/d** (draw) (1 dp each).
- CAPTION: "This number inherits every error in its inputs — read it beside the
  revision panel. A draw that survives two vintages of revisions is real; a draw that
  appears and disappears is measurement."

### G.3 Item 6.23 — Revision magnitude vs claimed imbalance
- SOURCE: Carollo ch. 6, Box 6.1 / Fig 6.5 (revisions exceed the imbalance debated).
- FORMULA: per balance month with ≥2 vintages: `revision = |latest − first_published|`
  world-demand estimate; plot vs |implied_balance| from G.2; `ratio = revision /
  max(|implied_balance|, 0.05)`.
- CHART: navy bars (revision, mb/d) with light-blue line (|implied_balance|).
- TEST: first vintage 104.0, latest 104.6 → revision **0.6**; |balance| 0.5 →
  ratio **1.2** (1 dp).
- CAPTION: "When the bar exceeds the line, the market is trading a number smaller than
  its own error term. Position sizing, not conviction, is the correct response to that
  regime."
- NOTE: panel shows "insufficient vintages" until ≥2 MOMR vintages exist — this
  project's Spec 06 already has 2 real vintages stored (July + August 2026, pulled
  during Spec 06's close-out) — same behaviour as the Spec 06 waterfall; do not fake
  history for any month still short of 2 vintages.

### G.4 Item 6.24 — Rigs → production lead/lag (EXTENSION — label it)
- SOURCE: thin in the library (Spurga gestures at supply response); primarily
  EXTENSION. The caption says so.
- INPUTS: Baker Hughes US oil rig count (Spec 06-D); EIA L48 crude production (Spec 05
  or Spec 01 monthly).
- BUILD: dual-axis — rigs navy vs production shifted back k months light blue; k =
  `regress.best_lag` over 0–9 months, printed in the caption.
- TEST: synthetic y(t)=x(t−5) → best_lag returns **5**.
- CAPTION: "Extension, not book doctrine: the lag itself drifts with DUC inventory and
  well productivity. Treat the reported lag as this cycle's answer, not a constant."

### 14-G ACCEPTANCE — tests green; call-on-OPEC cross-checked against one MOMR table by
hand for the latest month.

---

## SESSION 14-H — MACRO OVERLAYS + FREIGHT/AIS CAPTIONS + BAND-SHIFT MONITOR

### H.1 Item 10.46 — Uncertainty-index overlay
- SOURCE: "Forecasting crude oil prices: does global financial uncertainty matter?"
  (project library) — EPU/GPR/macro-uncertainty/EMV improve oil forecasts.
- INPUTS: FRED `USEPUINDXD` (daily EPU), `VIXCLS` (VIX) via the Spec 10 client; GPR
  from the Caldara–Iacoviello public CSV — verify the live URL at implementation time,
  fetch in a small `pipelines/gpr/` puller, document source + terms in the licences
  file; if the URL is unstable after a 30-min timebox, descope GPR with a note. §0.8.6
  reconfirms the GPR page/licence but the exact file URL should still be re-checked
  live at implementation time (file paths on that site have changed before).
- FORMULA: 3y rolling z-score per index.
- CHART: z-lines (EPU navy, VIX light blue, GPR grey) with WTI M1 on the right axis.
- TEST: value 180, mean 120, sd 40 → z = **1.50** (2 dp).
- CAPTION: "Uncertainty spikes raise the option value of inventories and widen risk
  premia; the paper's finding is about forecast error, not direction. Use as regime
  context for every other panel, especially positioning."

### H.2 Item 10.47 — Inventories-to-sales ratio
- SOURCE: Yamarone ch. 7 (MTIS; lag-in/lead-out duality).
- INPUTS: FRED `ISRATIO`; recession shading from FRED `USREC`.
- CHART: line with grey recession bands.
- TEST: inventories 2,520 / sales 1,800 = **1.40** (2 dp).
- CAPTION: "A rising ratio means production cuts ahead — bearish distillate/industrial
  oil demand with a lag; Yamarone: the ratio lags the cycle going in and leads coming
  out, because it encodes expectations."

### H.3 Item 10.48 — Leading demand proxies (minimal panel; drop candidate)
- SOURCE: Yamarone ch. 6 (NDCGXA leads capex 3–6 months; YoY not MoM).
- INPUTS: FRED `NEWORDER`, `INDPRO`.
- CHART: one small panel, two YoY % lines, zero dashed.
- TEST: 105.0 vs 100.0 → **+5.0%** (1 dp).
- CAPTION: "Orders lead capex by three to six months (Yamarone); industrial production
  is the coincident check. Oil relevance runs through distillate."

### H.4 Item 10.49 — Real oil price + dollar overlay
- SOURCE: Yamarone (CPI chapters) for deflation discipline; Bouchouev ch. 2 for the
  rates-as-carry linkage.
- INPUTS: `fut.cl.m1`; Spec 10 `deflate` helper (CPI); FRED `DTWEXBGS` broad dollar
  (confirmed live and current — §0.8.5; do NOT use the discontinued `DTWEXB`).
- CHART: real WTI navy (today's dollars, LHS); dollar index light blue RHS with the
  axis INVERTED and the axis title stating "(inverted)".
- TEST: nominal $40 at CPI 200 → current CPI 300 → real **$60.00** exactly (reuses the
  Spec 10 deflate toy test).
- CAPTION: "Oil priced in a strengthening dollar tightens the rest of the world before
  it tightens the US. The inverse correlation is loose and regime-dependent — the
  overlay is context, not a signal."

### H.5 Item 11.50 — Floating-storage interpretation (caption on the Spec 11-D panel)
- SOURCE: Johnson, floating-storage chapter; Bouchouev ch. 2–3.
- CAPTION (verbatim, added to the existing floating-storage proxy panel, plus a
  cross-link to the 7.30 breakeven band): "Floating storage is the most expensive
  storage tier — it appears only when contango beats vessel charter + financing, i.e.
  after land tanks saturate (see the carry breakeven band on page 07). The build is
  gradual; the unwind is a rush — when the contango closes, stored cargoes flood a
  barely-recovering market at discounts (Johnson). Rising floating storage confirms
  super-contango; its peak often precedes the spread's recovery. AIS-derived proxy:
  laden + idle ≥ N days, not confirmed storage."

### H.6 Item 11.51 — Freight-uncertainty note (caption on 7.33 accordion)
- SOURCE: Adland & Alizadeh (TC–FFA differential as freight convenience yield, widest
  in tight markets); Imsirovic ch. 12 (freight decides whether the arb works).
- CAPTION line appended to the accordion caption: "The reversion band must widen when
  freight is volatile; we proxy this statistically (rolling σ) because the dashboard
  carries no freight prices."

### H.7 Item X.52 — Band-shift vigilance (core seasonal standard)
- SOURCE: Wengler ch. 6 (seasonality functions had to be re-published as markets
  changed; gas grew a second summer peak when power burn arrived).
- BUILD: (a) append to the caption generator used by ALL seasonal panels: "Bands assume
  the seasonal shape is stable; structural change (capacity, exports, policy) shifts
  the shape itself. When the current year rides a band edge for months, suspect the
  band, not the year." (b) helper `seasonal_ext.band_shift_flag(series)` → TRUE when
  the trailing 12m of daily observations sits outside the 5y band on > 40% of days.
  (c) surface flagged series on the home freshness table as "band-shift candidates".
- TEST: synthetic series with a permanent level shift after year 4 → flag **TRUE**;
  a series inside the band → FALSE.

### 14-H ACCEPTANCE — tests green; home page shows the band-shift column; captions
H.5/H.6 visible on their pages; EURUSD/CPI cross-checks from Spec 10 still pass.

---

## MASTER DEFINITION OF DONE — SPEC 14

- [ ] 14-A curve suite live on page 07 (spreads, breakeven band, convexity, roll yield,
      convenience yield, 2020 annotation); M1–M6 history in lake
- [ ] 14-B coverage & balance-quality tab on page 01; Cushing utilisation +
      weeks-to-boundary; flow-map deviation colouring
- [ ] 14-C GRM, ratios, accordion, crack-lead, RV, spread-vs-inventory scatter on
      page 07; both crack hand-checks green
- [ ] 14-D COT pipeline idempotent; positioning dashboard + fragility flag +
      positioning-momentum with honest lag
- [ ] 14-E winter cover, fill trajectory, weather-adjusted surprise; corridor
      util/deviation on Sankey + map
- [ ] 14-F spark (2 heat rates), implied heat rate, switching scatter,
      temp-normalised load, SNSP curve
- [ ] 14-G OPEC overlay, call on OPEC, revision-vs-imbalance, rigs lead-lag
- [ ] 14-H uncertainty overlay, ISRATIO, leading proxies, real-price/dollar;
      AIS + accordion captions; band-shift monitor on home page
- [ ] Every panel carries its verbatim caption; every EXTENSION item labelled as such
- [ ] Nothing from §0.5 was built, proxied, or approximated
- [ ] All worked-number tests pass UNMODIFIED (grep the test files for: 26.25, 24.44,
      1.00, 48.7, 6.0, 800, 4.0, 200, 91.8, 0.20, 91.7, 5.00, 16000, 2.0, 27.0, 0.5,
      1.2, 5, 7.20, 24.00, 0.60, 0.98, 1.22, 0.40, 0.80, 1.60, 15.19, 1.200, 31.75,
      250, 1.50, 1.40, 60.00, 5.0)

---

## APPENDIX — Cumulative Register & Operator's Original Batching Notes

The operator's working notes for this spec existed first as an item-by-item brainstorm
(CONCEPT/SOURCE/MAPS TO/BUILD INSTRUCTION/Test/Interpretation-caption format) before being
reconciled into the lettered-session master file above. That brainstorm's actual panel
content, formulas, worked test numbers and captions are IDENTICAL to Sessions 14-A through
14-H above (same 26.25/24.44/48.7/0.98/1.22/24.00/7.20/... test numbers throughout) — it is
not repeated here to avoid two divergent copies of the same spec. The two pieces of that
draft genuinely worth keeping — a compact status register and a suggested first-batch
sequencing — are captured below.

### Cumulative register (status at spec-add time — update as sessions complete)
| # | Panel | Base spec | Master-file ref | Status |
|---|---|---|---|---|
| 1.1 | Days of forward cover | 01 | B.1 | specced |
| 1.2 | Stock-Δ vs price-Δ scatter | 01/07 | B.2 | specced |
| 1.3 | WPSR adjustment tell | 01 | B.3 | specced |
| 1.4 | Cushing utilisation | 01 | B.4 | specced |
| 1.5 | Weeks-to-boundary | 01 | B.5 | specced |
| 1.6 | Utilisation vs margin lag | 01/07 | B.6 | specced |
| 1.7 | Gasoline import split | 01 | B.7 | specced |
| 1.8 | Product supplied YoY | 01 | B.8 | specced |
| — | PADD flow-map colour/hover enhancement | 01 | B.9 | specced |
| 2.9 | Days of winter cover | 02 | E.1 | specced |
| 2.10 | Fill trajectory vs target | 02 | E.2 | specced |
| 2.11 | Weather-adjusted surprise | 02/08 | E.3 | specced |
| 2.12 | Summer–winter spread | 02 | §0.5 | dropped (needs TTF) |
| 3.13 | Corridor norm + utilisation | 03 | E.4 | specced |
| 3.14 | Nomination-gap rule | 03 | E.5 | specced (caption) |
| 4.15 | Spark spread US | 05 | F.1 | specced (adapt to CAISO/NYISO — see F.1 note) |
| 4.16 | Implied heat rate | 05 | F.2 | specced |
| 4.18 | Gas share vs price | 05 | F.3 | specced |
| 4.19 | Temp-normalised load | 04/05/08 | F.4 | specced |
| 4.20 | SNSP vs price | 04 | F.5 | specced |
| 6.21 | OPEC vs Brent overlay | 06/09 | G.1 | specced |
| 6.22 | Call on OPEC | 06 | G.2 | specced |
| 6.23 | Revision vs imbalance | 06 | G.3 | specced (Spec 06 already has 2 real MOMR vintages) |
| 6.24 | Rigs→production lag | 06 | G.4 | specced (extension) |
| 7.26–7.41, X.53 | Crack/curve/spread suite (12 panels + M1–M6 pull) | 07 | A.1–A.7, C.1–C.7 | specced |
| 9.42–45 | COT suite + event discipline | new `pipelines/cftc/` | D.0–D.4 | specced (needs COT pipeline; dataset id confirmed §0.8.1) |
| 10.46–49 | Macro overlays | 10 | H.1–H.4 | specced |
| 11.50–51 | AIS/freight captions | 11 | H.5–H.6 | specced (captions) |
| X.52 | Band-shift vigilance | core | H.7 | specced |
| 40 | Brent–Dubai EFS | — | §0.5 | dropped (needs Dubai swaps, paid) |
| — | Dark/clean spreads, TC–FFA, spare capacity | — | §0.5 | dropped (needs coal+EUA, Baltic data; no source) |

### Suggested first-batch sequencing (operator's original note, narrower-grained than
the Session 14-A/B/D split above — useful if 14-A feels too large for one sitting)
1. **Batch 1** (one weekend session): the M1–M6 futures-history pull enhancement (A.1)
   plus items 7.29/7.30/7.36 (A.2, A.3, A.5) — one code path (curve fetch/wide-format
   helper), three panels. A natural first slice of Session 14-A if it needs splitting.
2. **Batch 2**: items 1.1/1.4/1.5 (B.1, B.4, B.5) — one new EIA series id (Cushing
   working capacity, §0.4.1/§0.8.3), three panels. A natural first slice of 14-B.
3. **Batch 3** (weekday, ~1h): the COT mini-pipeline alone (D.0) — unlocks D.1–D.3 the
   following weekend once real data has accumulated for at least one week's report.

---

## GUARDRAILS (Claude Code, read before every session)
- Never edit `.env`. Never print key values. CFTC/FRED/GPR pulls must appear in
  cassettes with any query params that could identify the user filtered.
- Never add a dependency not named in this file or the base specs without asking.
  This spec adds NO new Python dependencies (statsmodels is NOT required — use
  numpy/scipy lstsq for the OLS items, or ask before adding statsmodels).
- If a formula's inputs are missing from the lake, STOP and report which series is
  absent — do not substitute, interpolate across sources, or invent.
- If a hand-checked test fails, the code is wrong. Fix the code, never the number.
