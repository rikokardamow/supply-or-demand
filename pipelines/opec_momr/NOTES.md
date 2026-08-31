# pipelines/opec_momr — notes

## Excel-first, per the spec's own rule
`specs/06_opec-supply.md` mandates: parse the Excel appendix first, Camelot PDF parsing
(Session B) is a fallback only for tables missing from Excel. This pipeline is Excel-only.

## Download URL — confirmed live, a public static file, no key
`https://opec.org/assets/assetdb/momr-appendix-{month}-{year}.xlsx` — lowercase full month
name (e.g. `momr-appendix-august-2026.xlsx`), found via the real MOMR page's DOM, not
guessed. The PDF's own "Download latest MOMR" link goes to a different, dynamic endpoint
(`https://momr.opec.org/pdf-download/`) — irrelevant here.

**A genuinely nonexistent month doesn't 404 cleanly** — opec.org's Cloudflare front returns
a `403` "Just a moment..." JS-challenge page instead (confirmed live via a deliberately
bogus month). `downloader.latest_appendix` treats *any* non-200 response for the current
month as "not published yet" and falls back one month, rather than branching on a specific
status code — this handles both a real 404 and this Cloudflare-flavoured 403 uniformly. If
even the prior month fails, that's raised as a genuine `RuntimeError` (the prior month
should always be available).

## Raw-file caching — a new precedent for this project
Every other pipeline here caches *parsed* data (e.g. `pipelines/entsog/directory.py` caches
a DataFrame as Parquet). This one caches the **raw downloaded `.xlsx` file itself** at
`data/raw/opec/momr-appendix-{month}-{year}.xlsx`, since the parser needs to re-read real
Excel structure from disk — a fetched month never changes once published, so a simple
"does the cached file exist" check (no age/mtime staleness window) is enough, unlike
`entsog`'s 30-day refresh.

## The workbook — 6 sheets, none a long monthly history
`Contents` + 5 data sheets. Every data sheet is a **snapshot/outlook table** (a handful of
years + trailing quarters + occasionally one or two specific actual months) — not deep
monthly history in any single download. This is exactly why `revision_date` = the MOMR's
own publication month matters: real history only accumulates by pulling every month and
keeping each vintage (`write_ts_long`'s revision-based de-dup naturally handles re-running
the same month idempotently).

| Sheet | `table_slug` | Content | Period columns (confirmed live, Aug 2026 issue) |
|---|---|---|---|
| `Table 11 - 1` | `demand_balance` | World demand (regional), Non-DoC production, **OPEC crude (secondary sources) — aggregate only**, OECD stocks, oil-on-water, days of forward consumption | `2023,2024,2025,1Q26..4Q27,2026,2027` |
| `Table 11 - 2` | `demand_balance_revision` | Same row layout as 11-1, but values are **OPEC's own precomputed deltas vs last month's table** | same as 11-1 |
| `Table 11 - 3` | `oecd_stocks` | OECD stocks (commercial/SPR, by region) + oil-on-water + days of forward consumption, more granular than 11-1 | `2023,2024,2025,3Q24..2Q26` |
| `Table 11 - 4` | `nondoc_production` | Non-DoC liquids production **by individual country** + DoC NGLs | `2025, "25/24" (change, skipped — not a period), 1Q26..4Q26` |
| `Table 11 - 5` | `rig_count` | World rig count by region/country | `2023,2024,2025,4Q25,1Q26,2Q26,` plus **two real `datetime` columns** (the latest 1-2 actual months, e.g. `2026-06-01`, `2026-07-01`) |

**Table 11-2 is a major simplification for the spec's revision-waterfall transform**: OPEC
already publishes "current minus prior vintage", row-for-row identical to Table 11-1's
layout — read it directly rather than diffing two stored vintages yourself.

**Confirmed gap, matches the spec's own two-session split**: no sheet has **per-country DoC
crude production** (Saudi/Iraq/UAE individually) — only the OPEC-wide aggregate (Table
11-1's `demand_balance.nondoc_liquids_production.opec_crude_oil_production_secondary_sources`
— note: mis-attributed to the "Non-DoC" section by the generic parser below, a known,
harmless quirk, not a data error, see "Section-tracking simplification"). This is exactly
what Session B's Camelot PDF fallback and the quota-compliance chart need.

## `ws.max_column` is unreliable
Table 11-4 reports 968 columns via openpyxl; only ~5 have real header values (phantom
formatting-only columns). Parsing keys off non-null header cells found while scanning for
period labels, never `ws.max_column`.

## Header-row position varies by sheet — detected, not hardcoded
Confirmed live: Tables 11-1/11-2/11-3 have their header at (0-indexed) row 4; 11-4/11-5 at
row 5 (a merged "Change" super-header sits above the real one). `_find_header_row` scans
the first 10 rows for one with ≥2 cells that parse as period labels, returning both the
1-indexed row number and the parsed `{col: (timestamp, freq)}` map. **Two real bugs were
caught by testing against the live file, not by design alone**: (1) annual headers are real
`int` cells (`2023`, not `"2023"`) — only quarter labels (`"1Q26"`) are strings, so
`_period_to_ts_freq` must check both; (2) data-row walking must start *strictly after* the
detected header row, or the header row's own year/quarter cells get misread as a data row's
values (its label-column text, e.g. `"World rig count"`, would otherwise spuriously become
a series with each period column's *header number* as if it were a value).

## Same representative timestamp, different granularity — a real collision
An annual column (`"2026"`) and a quarterly column (`"1Q26"`) both map to `2026-01-01`.
Confirmed live: without handling this, the two values silently collide under
`ts_long`'s `(series_id, ts)` de-dup key — one overwrites the other. Every `series_id` here
therefore ends in `.annual` / `.quarterly` / `.monthly` (`_series_id_with_freq`), so the
same underlying concept at different granularities never collides.

## Full-breadth capture — every row, not a curated subset
Per explicit direction: instead of a hand-picked `{label: series_id}` dict, every labelled
row with at least one real numeric value in any period column is captured. `series_id` is
built from each row's own section/hierarchy context so identical labels in different
sections stay distinct (e.g. "Americas" appears under both `world_demand` and
`nondoc_liquids_production` in Table 11-1).

**Section-tracking simplification, known and accepted**: for the single-label-column sheets
(11-1/2/4/5), "section" only updates on a genuine blank-period header row (e.g. "World
demand", "Non-DoC liquids production") and never resets otherwise. A handful of standalone
summary rows that follow a section without their own header row (e.g. `DoC NGLs`, `OPEC
crude oil production (secondary sources)`, `Balance...` in Table 11-1) get attributed to
whichever section came before them in the sheet, which is conceptually slightly wrong (they
aren't really part of "Non-DoC liquids production") — but every such label is distinctive
enough on its own that this never causes an actual `series_id` collision, only a slightly
odd-looking prefix. Documented here rather than fixed with a larger hand-maintained
section map, since the risk is cosmetic, not a data-correctness bug.

**Table 11-3 needed a different strategy** — it's genuinely 3 levels deep across only 2
label columns: a top section (column B, no data of its own, e.g. `"Closing stock levels,
mb"` vs `"Days of forward consumption... days"`) containing column-B sub-items with their
*own* aggregate value (e.g. `"OECD onland commercial"`) which break down further into
column-C leaves (e.g. `"Americas"`). Two different top sections can share an identical
column-B/C breadcrumb (`OECD onland commercial > Americas` exists under *both* stock levels
and days-of-consumption) — confirmed live as 204 real `(series_id, ts)` collisions before
this was handled; `_parse_two_label_sheet` tracks the top section separately from the
breadcrumb specifically to prevent this.

## Unit varies within a single sheet
E.g. Table 11-1 is mostly `mb/d`, but its `"OECD closing stock levels, mb"` section is `mb`
and its `"Days of forward consumption..., days"` section is `days`. `_infer_unit` scans each
section-header label for a unit keyword (`mb/d`, `mb`, `days`, `units`), falling back to the
sheet's own default otherwise.

## Known simplification: `geo` is always `"WORLD"`
Even though many rows are genuinely country-level (Table 11-4/11-5's per-country
production/rig-count breakdowns). The location detail still lives in `series_id` (e.g.
`momr.nondoc_production.us.quarterly`) for anyone filtering by it — proper per-row
geo-tagging would need a country-name canonicalisation pass (matching country names to a
fixed code list), out of scope for this session; revisit if a chart specifically needs
`geo`-based filtering rather than `series_id`-based.

## Fixture test — a new precedent (`tests/fixtures/`)
The real August 2026 appendix (145 KB, already small) is checked in at
`tests/fixtures/opec_momr/momr-appendix-august-2026.xlsx` — `tests/test_opec_momr_parser.py`
parses it directly (no network, no vcrpy — a local file, not an HTTP call) and includes two
deliberate-corruption tests (a renamed anchor row, a mangled sheet title) confirming the
fail-loudly `ValueError`s actually fire.

## Verified (Session A)
Real pull: 2,052 rows across 421 series from one MOMR issue. Acceptance criterion met:
parsed 2026 annual world demand = 105.739323 mb/d, matching the real Table 11-1 cell value
exactly (this is also the headline "2026 world oil demand forecast" figure OPEC's own MOMR
reports). Oil-on-water and OECD stocks by region (the freight-adjacent pieces) both
captured. `pytest`/`ruff`/`mypy` all clean.

## Session B — per-country DoC crude production, without Camelot after all

The spec calls for a Camelot lattice-mode PDF parse as the fallback for the one table
genuinely missing from Excel (per-country DoC crude production, confirmed in Session A).
**Tried it, live, in this order, before writing any Camelot code:**
1. `momr.opec.org/pdf-download/` (the PDF's own download link) returns a **403** — a
   different, less stable endpoint than the Excel appendix's clean static URL.
2. Camelot's lattice mode needs a system **Ghostscript** install (not a pip package) — this
   needed the user to manually run the installer and approve a Windows UAC prompt (this
   automated session can't click through UAC itself). Confirmed installed successfully
   (`gswin64c.exe --version` → `10.07.1`) after that.
3. With a real MOMR PDF in hand (user-provided, since step 1 is blocked) and Ghostscript
   installed, the underlying premise turned out to be moot: **the MOMR PDF has a full,
   clean, digitally-native text layer, not a scan** — `pypdfium2`'s plain
   `get_textpage().get_text_range()` returns every row of Table 5-7 ("DoC crude oil
   production based on secondary sources, tb/d") as clean, regex-parseable text, with no
   image-based table-structure detection needed at all.

**Decision, per the spec's own "if unstable, stop and document" allowance**: parse the
PDF's embedded text directly (`pdf_parser.py`) instead of using Camelot — simpler, more
reliable (no lattice/stream-mode ambiguity, no Ghostscript runtime dependency for anyone
running this pipeline later), and verified accurate independently: summing every OPEC
member country this parser extracted for July 2026 (23,633) against the PDF's own printed
"Total OPEC" line for the same month (23,632) matched to within OPEC's own "totals may not
add up due to independent rounding" disclaimer — not a parsing error. Ghostscript stays
installed on this machine (harmless, and available if a future session ever does need
Camelot for a genuinely scanned document), but nothing in this codebase depends on it —
`camelot-py`/`opencv-python-headless`/`playa-pdf` were installed then **uninstalled again**
once this was confirmed, so they're not project dependencies.

**Real parsing gotchas, found by testing against the live file**:
- Table 5-7's data rows appear in the extracted text **after** both its own title *and*
  the next table's title (Table 5-8, "based on direct communication") — a two-column PDF
  layout quirk (captions read first, then each table's actual data block). The real anchor
  for where the data starts is the `"Secondary Change"` / `"sources <periods>"` header pair
  that follows the narrative paragraph, not literal proximity to the `"Table 5 - 7"` string.
- Header periods are two annual + three quarterly + **the latest 3 actual months** (this
  issue: May/Jun/Jul 2026) — the month columns are two space-separated tokens each (`"May
  26"`), and "26" alone is ambiguous about century, so the real calendar months are
  cross-anchored from the page's own narrative sentence (`"Total DoC crude oil production
  averaged 37.66 mb/d in July 2026..."`) rather than guessed.
- Every data row has **one more value token than period columns** — a trailing
  `"Jul/Jun"`-style change column with no corresponding header entry (mirrors the Excel
  appendix's own change columns, e.g. Table 11-4's `"25/24"`, which are similarly skipped).
- `".."` is OPEC's own "not available" marker (confirmed live in Table 5-8's messier
  direct-communication rows) — dropped, not treated as zero or an error.
- Table 5-8 additionally has footnote-asterisked alternate figures for Saudi Arabia
  (`"7.010*"`) — not parsed here at all; only Table 5-7 (secondary sources) is, matching
  the spec's own example series_id (`momr.prod.saudi.secondary`).

**Unit and `geo` differ from the Excel appendix parser**: `tb/d` (thousand barrels/day,
matching `quotas.csv`'s `kbd` convention directly, no conversion needed) rather than
Excel's `mb/d`; `geo` is the real country name here (e.g. `"Saudi Arabia"`), not the
Excel parser's `"WORLD"` simplification — per-country compliance is this table's entire
point. `series_id` convention: `momr.doc_crude_secondary.{country_slug}.{freq_word}`.

## `quotas.csv` — hand-maintained, sourced from OPEC's own press release
No quota/reference-production table exists anywhere in the MOMR itself (checked: searched
every page for "quota"/"baseline"/"voluntary adjustment", found only unrelated economic-
outlook prose). The spec's own data model already anticipated this
(`pipelines/opec_momr/quotas.csv`, hand-maintained). Seeded from OPEC's own 2 August 2026
press release (the "Voluntary 8" group's September 2026 required-production table) —
**published as an embedded PNG image on opec.org's press-release page, not HTML text or a
PDF table** (confirmed live: no `<table>` elements on the page at all, just one `<img>`),
read visually to transcribe the 7 real figures into the CSV.

**Known coverage gap**: only 7 of the group's countries appear in these monthly increment
announcements (Saudi Arabia, Russia, Iraq, Kuwait, Kazakhstan, Algeria, Oman) — UAE, also
part of the "Voluntary 8", already reached its own separately-negotiated ceiling earlier
and isn't part of the recurring monthly-adjustment table. Every other DoC country (Nigeria,
Congo, Gabon, Equatorial Guinea, Libya, IR Iran, Venezuela, and the non-OPEC DoC members)
has no current "quota" figure seeded at all — they either have no formal target under the
current framework or one wasn't readily available from a single primary source in this
session's timebox. **This file needs ongoing manual updates** as OPEC+ announces new
monthly levels (roughly monthly, per the group's own meeting cadence) — it is explicitly
not a "set once" file.

## `transforms.py::production_vs_quota` — a known simplification
Compares the latest *actual* production month against each country's most recently
announced quota row, **regardless of whether their reference months match** — OPEC+
announces a month's target about a month ahead of when it takes effect (this session: the
September 2026 target vs. July 2026 actuals, a ~2-month gap by the nature of the
announcement cycle). A precise point-in-time comparison would need `quotas.csv` to carry a
full history matched to each actual month; revisit if that becomes the sole open item.

## `transforms.py::revision_waterfall` and new chart primitives
Reads `Table 11-2`'s already-precomputed deltas directly (Session A's own finding — OPEC
publishes "current minus last month" itself; nothing here re-derives it from two stored
vintages). `core.theme.production_vs_quota_chart` (grouped bars, navy actual / grey quota,
compliance % as bar-top text) and `core.theme.revision_waterfall_chart` (`go.Waterfall`,
navy up / red down) are both new, reusable house-style primitives — a new `GREY = "#95a5a6"`
constant was added alongside the existing `NAVY`/`LIGHT_BLUE`/`RED`/`ORANGE` for the quota
bars, since no solid grey fill colour existed yet (only semi-transparent line greys).

## Verified (Session B)
Real PDF pull: 176 rows across 22 countries. Production-vs-quota and revision-waterfall
both render live with real data on page `06_supply.py`, verified in-browser (grouped bars
with correct compliance %, e.g. Oman 110%, Saudi Arabia 70%; waterfall with real
positive/negative bars for 2026 annual, OPEC's own most-revised year at time of writing).
`pytest`/`ruff`/`mypy` all clean.
