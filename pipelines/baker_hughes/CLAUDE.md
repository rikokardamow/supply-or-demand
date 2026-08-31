# Baker Hughes rig count — pipeline notes

Weekly North America rig count (`specs/06_opec-supply.md`, Session D). Friday entrypoint:
`pipelines/baker_hughes/pull_rigs.py`.

## No guessable URL (unlike OPEC's MOMR appendix)

The current XLSX lives at `rigcount.bakerhughes.com/static-files/{uuid}` — a fresh random
UUID every week, confirmed live. There is no date-based pattern to construct.

The only reliable way to find the current file is to scrape the landing page,
`https://rigcount.bakerhughes.com/na-rig-count`, and find the `<a>` whose exact text is
`"North America Rig Count Report - New Report"`. This is a stable label Baker Hughes itself
uses to mark the current report, distinct from the archived
`"...(2013-Aug 2025)"`-suffixed one sitting right next to it in the DOM. Matching on link
text rather than position/order is what makes this robust to the page adding more archived
entries over time.

## HEAD before GET

`download_current_report()` resolves the report date via a **HEAD** request first —
confirmed live that this server returns the identical `Content-Disposition` header on HEAD
as on GET, with no response body. Only falls through to a full GET (~8 MB) on an actual
cache miss. A naive GET-then-check-cache design would download the full file every single
run just to read its date.

The report date itself comes from the response's `Content-Disposition` filename (e.g.
`"08-28-2026 North_America Rig_Count Report.xlsx"`), not from "today" — the file can be a
few days newer or older than the run time depending on exactly when this executes relative
to Friday's publication.

## `NAM Weekly` sheet — already a long table, not a snapshot

Unlike OPEC's MOMR appendix (snapshot/outlook tables needing a `revision_date`-per-vintage
scheme), this sheet is already row-per-observation: confirmed live, ~188,000 rows covering
~2.7 years of history, columns `Country, County, Basin, GOM, DrillFor, Location,
State/Province, Trajectory, Year, Month, US_PublishDate, Rig Count Value`. No revision
tracking is needed — `revision_date` is just ingestion time (matches `pipelines/eia`'s
convention for series with no per-row vintage info). Running the Friday entrypoint weekly
naturally keeps the lake current, and `write_ts_long`'s revision-based de-dup makes
re-running it idempotent (confirmed: identical row/series counts across two consecutive
runs).

10 blank/title rows precede the real header — `parser._find_header_row` detects it by
scanning for the first row whose first cell is literally `"Country"`, rather than
hardcoding a row number.

## Aggregation: 3 levels, not full per-county granularity

Per-county is excessive for any current chart need (and can be added later straight from
the cached raw file in `data/raw/baker_hughes/` if it turns out to matter). Aggregated to:

- `bh.rigs.<country>.total` — country total, everything summed
- `bh.rigs.<country>.<drillfor>` — e.g. `bh.rigs.united_states.oil`, matching the spec's
  own example series_id exactly
- `bh.rigs.<country>.<drillfor>.<state>` — one level of regional detail

## Confirmed real values (2026-08-28 report)

US oil rigs = 447, US total (oil + gas + miscellaneous) = 588. Both plausible against
public reporting at the time.

## Known simplification

Rig count vs. WTI on the dashboard (`apps/dashboard/pages/06_supply.py`) is a single navy
series only — the spec's own text notes WTI joins "once Spec 07 exists"; there is no WTI
series in the lake yet.
