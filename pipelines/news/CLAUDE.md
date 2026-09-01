# pipelines/news — Claude Code Guide

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

## Tagging is deliberately split across sessions — don't conflate the two
Session A (this session) does the simplest possible "tagging": each row's `tags` is
`[event_type]` straight from the curated query dictionary (`queries.py`) that matched it,
and `severity` is a fixed placeholder (`events.py::SESSION_A_SEVERITY_DEFAULT = 1`). This
satisfies the spec's own Session A acceptance criterion ("a real crude-outage query
returns tagged rows in the lake") without yet building the fuller regex/keyword-tier/
geo-dictionary tagging engine, which is explicitly `specs/09_news-events.md`'s Session B
scope (multi-tag extraction from headline text, severity 1-3 by keyword tier, geo via a
country-name dictionary). Don't re-derive tags/severity from headline text in Session A
work — that engine belongs in a later, separate module.

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
full article URL (`hashlib.sha256(url.encode()).hexdigest()`), matching root `CLAUDE.md`'s
own `events(event_id=hash(url), ...)` schema description. Stable across re-pulls of the
same article (needed for `write_events`' dedup to actually work on repeat runs).

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
