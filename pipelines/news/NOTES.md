# pipelines/news — notes

## GDELT DOC 2.0 — free, no key, confirmed live response shape
`GET https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json&
maxrecords=...&timespan=7d`. Real JSON shape (confirmed live, not the spec's generic
description):
```json
{"articles": [
  {"url": "...", "url_mobile": "", "title": "...", "seendate": "20260831T233000Z",
   "socialimage": "...", "domain": "eluniversal.com", "language": "Spanish",
   "sourcecountry": "Venezuela"}
]}
```
No `source`-as-outlet-name field — only `domain`. `seendate` is a compact, non-ISO
timestamp: `%Y%m%dT%H%M%SZ` (no separators) — `pd.to_datetime(s, format=...)` needed, not
a bare `pd.to_datetime(s)`. No tags/severity/commodity in the raw response at all — this
project's own job entirely (see "Tagging" below).

## `api.gdeltproject.org` is genuinely, severely flaky — confirmed live, not assumed
Over ~10 manual attempts while building this pipeline: most calls hung until a long
connect-timeout (30-60s), some failed instantly with a connection reset, and only roughly
1-in-3 succeeded with real data within 45s. Confirmed this is the endpoint itself, not a
local network block, by successfully fetching `www.gdeltproject.org` on every attempt
while `api.gdeltproject.org` failed most tries in the same session. This matches GDELT's
well-known real-world reputation (a single heavily-loaded Google-Cloud-hosted endpoint
serving enormous global query volume).

`client.py::GDELTClient._get` is designed around this: a 45s per-request timeout
(`REQUEST_TIMEOUT_SECONDS`), up to 6 retries (`MAX_RETRIES`) with exponential backoff
starting at 5s and capped at 60s, catching the broad `requests.exceptions.
RequestException` (covers every failure mode actually observed live — connect-timeout,
connection reset, and a genuine `HTTPError` on some non-2xx status too — not just HTTP
5xx, unlike `pipelines/entsoe/client.py`'s narrower retry which only needed to handle
503s). A **single query pull can legitimately take several minutes** in the worst case
(multiple 45s timeouts plus growing backoff) before either succeeding or exhausting
retries — this is expected, not a bug, given how flaky the endpoint really is.

**Per-query resilience on top of per-request retry is essential, not a nice-to-have —
confirmed by two real full-pull runs**: the first `pull_news.py` run had only 2 of 6
curated queries succeed within their retry budget (`crude/outage`, `crude/opec`; the
other 4 failed with a mix of `ReadTimeout`/`HTTPError`/`ConnectTimeout`); a second run
minutes later had the *opposite* pattern — 5 of 6 succeeded, with a different query
(`crude/outage`) the one that failed this time. `pull_news.py::pull_news` catches
`requests.exceptions.RequestException` per curated query individually (same precedent as
`pipelines/entsoe/pull_actuals.py`'s per-zone/per-indicator resilience) so one query
exhausting its retry budget never aborts the rest of the (≤10-query) pull — without this,
a realistic run would frequently return zero rows rather than a partial success.
Re-running `pull_news.py` picks up whatever failed last time; `write_events`' dedup on
`event_id` (a stable hash of the URL) makes this naturally idempotent.

## GDELT also rate-limits via a 200 response, not just 429 — confirmed live in the cassette
Recording `tests/cassettes/test_news_client/...yaml` live, the *first* request came back
as a genuine HTTP 200 whose body was plain text, not JSON: `"Please limit requests to one
every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries..."`. This is
GDELT's own request-pacing rate limit, returned as a 200 rather than a 429 — a different
failure mode from the connect-timeout/reset flakiness above, and one that would silently
slip past any retry logic that only checks HTTP status codes.

`client.py::GDELTClient._get` happens to already handle this correctly, though not by
deliberate design for this specific case: `response.raise_for_status()` doesn't fire (the
status is 200), but the following `response.json()` call raises
`requests.exceptions.JSONDecodeError` on the plain-text body — confirmed live that this
exception **is** a subclass of `requests.exceptions.RequestException` (via
`InvalidJSONError`) in the installed `requests` 2.34.2, so `_get`'s existing broad
`except requests.exceptions.RequestException` catches it and retries same as any other
transient failure. The second attempt in the same recording succeeded with real data.
**Do not narrow that except clause to only network-level errors** (e.g.
`ConnectionError`/`Timeout`) without also explicitly handling this 200-with-text-body
case — it would silently stop retrying and instead crash on `payload.get("articles",
[])` being called against a string, or worse, misparse.

## Tagging (Session B) — headline-derived, replacing Session A's placeholder
`tagging.py` derives `tags`/`geo`/`severity` from an article's own headline text via
regex/keyword dictionaries (`events.py` no longer uses Session A's `tags=[event_type]`/
`severity=1` placeholder). `commodity` still comes from the query dictionary
(`queries.py`) unchanged — only `tags`/`geo`/`severity` are re-derived per article.

**`event_type` is unioned into the headline-derived tags, not replaced by them**
(`events.py::_merge_tags`) — the query match itself is real evidence the article is
relevant even when the headline text doesn't literally contain one of `tagging.py`'s
own keywords (an oblique headline, or a query that matched on article body text
GDELT/Guardian don't expose). Every row always gets at least the query's own
`event_type` tag, enriched with whatever else the headline scan finds.

**Severity tiers had to diverge from the spec's literal wording to pass its own
acceptance test**: the spec names tier 3 as "force majeure/explosion/embargo", tier 2
as "outage/strike" — but its own crafted acceptance headline ("refinery fire ...")
needs severity >=2, and "fire" isn't literally one of those named words.
`SEVERITY_3_KEYWORDS` includes `fire`/`blast` alongside `explosion` (the same kind of
physical-incident severity), which is what actually makes
`tests/test_news_tagging.py::test_refinery_fire_rotterdam_acceptance_case` pass.

**Headline-derived geo deliberately overrides GDELT's/Guardian's own publisher-country
field** (`sourcecountry` for GDELT, a fixed "United Kingdom" for Guardian — see below):
both are the *publisher's* country, not necessarily the event's own location (a US wire
story about a Rotterdam refinery fire would otherwise wrongly geo-tag as the US, not
NL). `GEO_KEYWORDS` is a small, deliberately non-exhaustive city/country dictionary
covering common oil/gas hubs seen in this pipeline's own curated queries — not a
general-purpose gazetteer. When no keyword matches, `geo` falls back to the raw
publisher-country string as-is, which means the column can hold **either** a 2-letter
code (headline-derived) **or** a full country name (fallback) — a known, accepted
format inconsistency, not a bug; revisit with a proper name-to-code table if this ever
matters for a filter panel or map.

**Regex word-boundary matching needed the *end* boundary dropped, confirmed by a
failing test**: `\bkeyword\b` rejects simple plural/inflected forms (`\bsanction\b`
doesn't match "sanctions" — no word boundary between "sanction" and its trailing "s").
`tagging.py::_contains_any` anchors only the *start* (`\bkeyword`, no trailing `\b`),
which still correctly rejects a keyword appearing mid-word (`\bhalt` doesn't match
inside "asphalt" either, since there's no boundary immediately before "halt" there).

## Fuzzy cross-source dedup (Session B) — catches what exact-URL dedup can't
`dedup.py::drop_fuzzy_duplicates` catches two *different* outlets' distinct URLs
covering the same real-world event with a similar headline — something neither
`write_events`' `event_id` dedup nor `events.py::merge_cross_query_duplicates` can catch,
since both key off the URL, and GDELT/Guardian articles about the same story always
have different URLs. Per the spec: `rapidfuzz.fuzz.token_sort_ratio` >= 90 within a 48h
window counts as the same event; only the earliest report is kept. Compares each row
only against still-kept rows within its own rolling 48h window (not globally N-by-N).

**`token_sort_ratio` is case-sensitive by default — confirmed live, not assumed**: two
otherwise-identical headlines differing only in capitalization scored 68.6, not 100.
Different outlets rarely share the same capitalization convention (title case vs.
sentence case), so comparing raw headlines would systematically under-match real
duplicates — both headlines are lowercased before comparing.

## Guardian Open Platform (Session B) — same client interface, live verification pending
`guardian_client.py::GuardianClient.search(query, page_size)` returns the same column
shape as `client.py::GDELTClient.search` (url, title, seendate, domain, language,
sourcecountry) so `pull_news.py` can loop both sources uniformly. Built against
Guardian's own public, versioned API reference
(https://open-platform.theguardian.com/documentation/), **not a live-confirmed
response** — `GUARDIAN_KEY` was empty in `.env` throughout this session. Unlike GDELT,
Guardian is documented as production-safe (no observed/expected flakiness), so its
retry is lighter (3 attempts, capped 30s backoff) than GDELT's.

**Still needs live confirmation once a real key exists**: the exact `results[]` field
names assumed here (`webUrl`/`webTitle`/`webPublicationDate`); whether Guardian's `q`
param actually supports the same boolean-query syntax as GDELT (`queries.py`'s curated
queries use parentheses/OR/quoted-phrase syntax written for GDELT — Guardian's own
query syntax may be simpler and not support all of it, in which case some queries might
return fewer/different results than intended, not necessarily zero); whether
`content-type=article` or similar filtering is worth adding to exclude non-article
result types. `tests/test_news_guardian_client.py` covers the parsing logic against a
crafted response, not a real cassette — no cassette exists for this client yet.
`pull_news.py::main` gracefully skips Guardian entirely (prints a message, doesn't
crash) when `GUARDIAN_KEY` is unset, so the pipeline stays fully runnable GDELT-only
until a key is added.

## Page `09_events.py` (Session B)
Filterable event table (commodity multiselect, tag multiselect, minimum-severity
selectbox, time-range pill) + an events-per-week bar chart
(`core.theme.count_bar_chart`, new — a plain navy bar-per-period primitive, since no
existing chart function fit a simple count-over-time shape). Overlaying event markers
onto other pages' charts (01/02/07) is explicitly Session C's job, not built here.

## Cross-query duplicate merge — a real gotcha, not hypothetical
The same article can genuinely match more than one curated query in a single run (e.g. a
headline mentioning both "OPEC" and "sanctions" matches both the `opec` and `sanctions`
queries) — each match produces its own single-tag `events` row for the *same* `event_id`
(the URL hash is deterministic, so both rows collide on the same key).
`core.storage.write_events`' dedup (`_write_partitioned`'s `dedup_subset=["event_id"]`,
keep-last) would silently keep only one query's single tag and drop the other match
entirely if rows were written as-is. `events.py::merge_cross_query_duplicates` unions
`tags` across same-`event_id` rows *before* `write_events` ever runs, so a
cross-matched article ends up with e.g. `tags=["opec", "sanctions"]` in one row, not two
competing single-tag rows.

## `events` is this codebase's first list-typed lake column
`core/schemas.py::EVENTS_SCHEMA`'s `tags` field is `pa.list_(pa.string())` — every other
schema (`ts_long`, `flows`) is purely scalar. Confirmed live: a DataFrame with a
Python-list-of-str `tags` column round-trips cleanly through `pandas.to_parquet`/
`read_parquet` and DuckDB's `read_parquet` with no special handling — pyarrow infers
`list<string>` automatically from non-empty lists.

**The real empty-frame gotcha turned out to be dtype, not list-type inference**: a plain
`pd.DataFrame(columns=[...])` (no data) leaves every column, including `ts`, as dtype
`object` — `validate_events` then fails on `ts` needing to be datetime64, confirmed live
by a failing test (`test_articles_to_events_empty_input_returns_empty_conformant_frame`).
Fixed the same way `core/storage.py::_read` already handles an empty dataset:
`EVENTS_SCHEMA.empty_table().to_pandas()` builds a correctly-typed empty frame straight
from the pyarrow schema, rather than a bare column-name list. The
list-type-inference-mismatch risk flagged during planning (`list<null>` vs
`list<string>` across write batches) was never actually triggered, since
`articles_to_events` never produces an empty tags list in practice (every row gets at
least `[event_type]`) — worth remembering if a future change ever allows an empty tags
list through.

## Reading `tags` back gives a numpy array, not a Python list
Confirmed live (caught by a failing test, not anticipated): `read_events()`'s `tags`
column comes back from DuckDB as a numpy `ndarray` per row, not a plain Python `list` —
`result.iloc[0]["tags"] == ["outage"]` raises `ValueError: The truth value of an array
with more than one element is ambiguous` rather than returning `True`/`False`. Any code
comparing or equality-checking a `tags` value read back from the lake needs
`list(result.iloc[0]["tags"]) == [...]`, not a bare `==`. Writing `tags` (a genuine
Python list, going into `write_events`) is unaffected — this is a read-path quirk only.

## `event_id` — sha256 of the URL, not GDELT's own identifier
GDELT's DOC 2.0 API assigns no article ID of its own — `events.py::_event_id` hashes the
full article URL (`hashlib.sha256(url.encode()).hexdigest()`), matching root `NOTES.md`'s
own `events(event_id=hash(url), ...)` schema description. Stable across re-pulls of the
same article (needed for `write_events`' dedup to actually work on repeat runs).

## Verified (Session B)
A real `pull_news.py` run (5 of 6 GDELT queries succeeded; Guardian gracefully skipped,
no key configured) wrote/refreshed 895 rows this run, bringing the lake to 1462 total
events (unique `event_id` count == row count — dedup still holds). Real severity
distribution across the whole lake: 1423 tier-1, 30 tier-2, 9 tier-3 — a small,
plausible-looking minority of genuinely severe headlines, not an even/arbitrary split.
`geo` shows a healthy mix of full country names (the `sourcecountry` fallback) and,
confirmed live, correctly-overridden 2-letter codes for headline-mentioned hubs.

**A real, accepted data-quality gap found while investigating**: 24 rows have
`geo=""` (empty). Traced to specific non-English headlines (Portuguese/Ukrainian/
Russian) where GDELT's own `sourcecountry` field was itself empty for those articles
and no `GEO_KEYWORDS` entry matched either — not a bug in `extract_geo` (verified live
that the same function correctly resolves e.g. a Hormuz-mentioning headline to "IR" in
isolation). Some of these rows are simply old — written by an earlier run before this
session's tagging engine existed, and never re-fetched since (GDELT's `timespan=7d`
window ages articles out of future runs) — an inherent property of an incrementally
accumulating, dedup-on-write lake (same as `ts_long` series elsewhere in this project),
not something a full historical reprocess would be worth doing for Session B's scope.

Page `09_events.py` verified live in-browser: time-range pill, commodity/tag
multiselects, and the min-severity selectbox all correctly narrow both the bar chart
and the table's row count together (e.g. filtering to `crude` + severity>=2 correctly
dropped the table from 1462 to 28 rows and the chart bars from ~600/300 to ~13/15); the
table itself renders real, genuinely multi-language headlines (Chinese, Arabic,
Vietnamese, Korean confirmed visible) with populated tags/severity/geo columns; no
console errors.

## Event overlay (Session C) — `apps/dashboard/components/event_overlay.py`

**Page target substitution, documented per the descope convention**: the spec names
pages 01 (crude), 02 (gas), 07 (cracks) — Spec 07 (refinery cracks) is still deferred
(needs a local IB Gateway, per `specs/07_refinery-cracks.md`'s own prerequisite, not
set up on this machine — see the Spec 07 entry in `README.md`'s build log). Page 06
(OPEC/global supply, commodity `crude`) substitutes for it — the closest thematic match
among already-built pages (sanctions/OPEC/geopolitics events are exactly what page 06's
own charts are about), not an arbitrary pick. Revisit once Spec 07 actually gets built.

**`add_event_markers` calling `fig.add_vline()` once per event hangs the page —
confirmed live, not a theoretical concern**: with 960 real `commodity="crude"` events
in the lake, page 01's Stocks tab never finished rendering (no error, just an
indefinitely spinning "Stop" button) until killed. `fig.add_vline()` does non-trivial
internal validation work *per call*, so a Python-level loop over hundreds of events is
also O(n) expensive on the Plotly side, not just O(n) in Python. Fixed by building a
plain list of shape dicts and setting them via a single `fig.update_layout(shapes=...)`
call instead — confirmed live this renders instantly regardless of event count.

**`min_severity` defaults to 2, not 1 — a deliberate signal-vs-noise choice, not just a
performance one**: tier-1 "general" events are the large majority of what's ingested
(1423 of 1462 total, confirmed live) and would visually bury a chart in low-signal
dotted lines even if rendering were instant. `MAX_MARKERS` (50, keeping the most
*recent* qualifying events) is a second, independent hard cap, since even a
severity-2+-only set could keep growing over time as more sessions' worth of news
accumulates.

**Two x-axis conventions needed supporting, confirmed by checking real chart code
first rather than assuming one convention**: most of this dashboard's charts
(`seasonal_range_chart`, used on pages 01/02/05) plot against **day-of-year**, not a
real calendar date, to overlay multiple years on one x-axis — `fig.add_vline(x=<a real
timestamp>)` would silently misplace or fail to plot at all on those charts. `x_axis=
"doy"` converts each event's `ts` the same way `apps/dashboard/pages/08_weather.py`
already does inline (`ts.replace(year=core.seasonal.REFERENCE_YEAR).dayofyear`) — a Feb
29 event has no equivalent day in the non-leap `REFERENCE_YEAR`, silently dropped
(`_doy` returns `None`) rather than crashing the whole page.

**Hover-marker tooltip clips at the very top of a card, confirmed live, not fixed**:
placing the invisible hover-scatter trace at `y=1` on the dedicated 0-1 marker axis
means its tooltip can render partially above the chart's own card boundary (visually
confirmed on page 01 — the tooltip's first line was cut off by the card edge). Left
as a known minor cosmetic issue, not a functional one (the tooltip text itself, once
visible, is correct) — revisit if this bothers a real reader in practice.

## Verified (Session C)
Confirmed live on all three target pages after the `add_vline`-loop fix: page 01's
Stocks tab (day-of-year x-axis) renders instantly with a visible orange (severity-2)
dotted line and a working hover tooltip (a real headline, confirmed visible, if
partially clipped by the card boundary — see above); page 02's gas storage page
renders correctly showing *no* markers, since zero `commodity="gas"` events currently
have `severity>=2` (a real data characteristic, not a bug — confirmed by checking the
lake directly); page 06's Oil-on-Water chart (real-date x-axis) shows the same
orange dotted line as page 01. No new browser console errors on any of the three pages
beyond the pre-existing, unrelated Plotly/dev-server noise already documented elsewhere
in this project's session history.

## Verified (Session A)
Two real, independent `pull_news.py` runs (a few minutes apart): run 1 wrote 409 event
rows (2 of 6 queries succeeded; 3 articles were cross-matched by both the `outage` and
`opec` queries and correctly merged into single two-tag rows via
`merge_cross_query_duplicates` rather than becoming two competing single-tag rows); run 2
wrote up to 1374 total rows (5 of 6 queries succeeded this time, including `crude/opec`
again with the identical 162-article count as run 1). **Idempotency confirmed
concretely, not just assumed**: after both runs, `read_events()`'s unique `event_id`
count exactly equals its row count (1374 == 1374) — zero duplicate rows despite the same
`crude/opec` query genuinely re-fetching a heavily-overlapping set of articles the second
time. Acceptance criterion met: a real crude-outage query (`crude/outage`, run 1) returned
250 real articles, each with `tags=["outage"]`, `commodity="crude"`, `severity=1` —
"tagged rows in the lake" per the spec's own Session A wording, via the query
dictionary's own commodity/event_type (the fuller keyword/severity/geo-dictionary
tagging engine is Session B's job, not re-derived here).
