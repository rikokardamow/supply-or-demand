# Spec 06 — OPEC / Global Supply Monitoring (MOMR + JODI + Baker Hughes)

**Weeks 8–9 · Est. 14–18 h (PDF parsing is the risk) · Prereq: Spec 00.**

## Objective & alpha question
OPEC+ production vs quota, non-OPEC supply growth, demand-forecast revisions, OECD stocks and
oil-on-water — tracked as *time series of revisions* the market underweights. Ties to Exhibit 1
(oil-on-water vs floating storage) and the supply narrative behind the refinery exhibits.

## Data sources
1. **OPEC MOMR** — monthly, ~11th–14th. PDF at `opec.org` (pattern
   `opec.org/assets/assetdb/momr-{month}-{year}.pdf` — verify each month) **plus Excel appendix
   tables. RULE: parse the Excel appendix first; use Camelot on the PDF only for tables absent
   from Excel.** Camelot: `uv add "camelot-py[cv]"` (needs ghostscript); `flavor="lattice"` for
   ruled tables, `stream` otherwise. Target tables: world oil demand, non-DoC supply, DoC crude
   production (secondary sources), OECD commercial stocks, oil-on-water.
   **Hard threshold from the master plan: if the Camelot parser eats >6 h total, abandon PDF
   parsing and live with Excel + JODI. Write the decision into this file.**
2. **JODI-Oil** — free monthly CSV (world DB) from jodidata.org data-downloads, ~20th. Bulk CSV →
   filter to crude production, refinery intake, closing stocks for majors.
3. **Baker Hughes rig count** — free weekly XLSX from rigcount.bakerhughes.com (N. America Fri
   ~noon CT; international monthly). Parse with pandas/openpyxl.

## Data model
All → `ts_long`, **with `revision_date` = MOMR publication month** so consecutive vintages coexist:
`series_id` like `momr.demand.world`, `momr.supply.non_doc`, `momr.prod.saudi.secondary`,
`momr.stocks.oecd`, `momr.oil_on_water`, `jodi.prod.crude.SA`, `bh.rigs.us.oil`.
Quota table: hand-maintained CSV `pipelines/opec_momr/quotas.csv` (country, effective_from, quota_kbd).

## Transformations
- Production vs quota gap + compliance % per DoC country.
- MOMR revision waterfall: current vintage − prior vintage per line item.
- Rig count YoY and 4-week change; oil-on-water YoY.

## Visualisation spec (page `06_supply.py`)
1. DoC production vs quota: grouped bars (navy actual, grey quota) + compliance % labels.
2. Demand-forecast revision waterfall (red down, navy up) across vintages.
3. Oil-on-water time series (navy area) — Exhibit-1 style; floating storage joins in Spec 11.
4. Rig count dual-axis: US oil rigs (navy) vs WTI (light blue, once Spec 07 exists; until then rigs only).

## Claude Code sessions

### Session A (weekend, 3 h) — MOMR Excel-first parser
> Read CLAUDE.md, specs/06_opec-supply.md. Scaffold `pipelines/opec_momr/`: downloader (verify the
> URL pattern for the latest issue, keep raw files in data/raw/opec/), Excel appendix parser
> mapping the target tables → ts_long with revision_date, schema validation that fails loudly on
> layout drift. Fixture test on one committed sample workbook (small, checked-in under tests/fixtures/).
> Acceptance: latest MOMR world-demand number matches the PDF headline.

### Session B (weekend, 3 h) — Camelot fallback OR skip + quotas
> Timebox 2 h: Camelot lattice parse for any target table missing from Excel; if unstable, stop and
> document. Then: quotas.csv seeded with current DoC targets, production-vs-quota transform +
> chart, revision-waterfall transform + chart on page 06.

### Session C (weekday, 1 h) — JODI
> `pipelines/jodi/`: bulk CSV download + filter to crude production/refinery intake/closing stocks
> for top-15 producers → ts_long. Monthly entrypoint.

### Session D (weekday, 1 h) — Baker Hughes
> `pipelines/baker_hughes/`: weekly XLSX ingest → ts_long; rig chart on page 06; Friday entrypoint.

## Definition of Done
- MOMR Excel tables ingesting with vintage tracking; ≥2 vintages stored; waterfall renders.
- Quota compliance chart live; JODI + rigs ingesting on schedule. PDF decision documented. Tests green.

## Stretch
- Auto-diff consecutive MOMRs → "silent revisions" alert list.
- IEA OMR free-summary headline scraper (numbers only, no paywalled content).
