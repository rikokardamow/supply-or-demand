# Spec 16 — NewsAPI.org Supplement (Manual Search Only)

**Est. 1 h · Prereq: Spec 09 (news pipeline). Independent — extends `pipelines/news/`,
does not touch the scheduled pull.**

## Objective & alpha question
Give the analyst a manual, on-demand way to pull additional headlines from NewsAPI.org
for a specific query — a fast supplement when GDELT/Guardian's curated query
dictionary misses something topical — while respecting the real licensing limit on
this particular source that Spec 09 already found and deliberately designed around.

## The real constraint — already found once, do not re-litigate it
Spec 09's own Definition of Done says, verbatim: **"NewsAPI absent from scheduled
pulls."** Its data-sources section adds: *"NewsAPI.org — free Developer tier is
dev/testing only (cannot be used in production), 100 req/day, 24 h delay. Use only
for local experimentation; never in scheduled pulls."* This dashboard's standard
pattern — `pull_daily.py`/`pull_weekly.py` run on a schedule per Spec 13 — **is**
production use of whatever data flows through it. A real `NEWSAPI_KEY` now exists in
`.env` (`settings.newsapi_key`, already a field since Spec 00) — that only means
manual/local experimentation is available, not that the ToS constraint has lifted.
**Do not add NewsAPI to `pull_news.py::main()` or any `pull_*.py` entrypoint.** If the
operator ever upgrades to a paid NewsAPI plan, revisit scheduling it properly
alongside GDELT/Guardian — record that decision here or in the README when it happens,
rather than silently starting to schedule it.

## Data source — real endpoint and params
`GET https://newsapi.org/v2/everything`

Query params this project will send:
- `q` — the operator's free-text query (from the manual-search UI, not the curated
  query dictionary in `queries.py` — this is a one-off ad-hoc search, not one of the
  ≤10 curated (commodity × event_type) queries GDELT/Guardian already cover).
- `pageSize` — `100` (NewsAPI's own per-page max).
- `sortBy` — `publishedAt` (most recent first — matches this project's own
  recency-first convention elsewhere).
- `apiKey` — from `settings.newsapi_key`.
- `language` — deliberately **left unset**. Setting it would silently exclude
  non-English results before they ever reach `translate.py`'s pipeline (the whole
  point of the news-map redesign's translate feature is surfacing non-English
  coverage) — the existing tagging engine already handles multi-language headlines
  fine without a language filter.

**Commonly-documented response shape** (from NewsAPI's own published reference —
treat as a strong prior, NOT yet confirmed against this project's real key):
```json
{"status": "ok", "totalResults": 123, "articles": [
  {"source": {"id": "reuters", "name": "Reuters"}, "author": "...",
   "title": "...", "description": "...", "url": "...", "urlToImage": "...",
   "publishedAt": "2026-09-03T12:00:00Z", "content": "..."}
]}
```
**Mandatory first implementation step**: confirm this shape with one real call
(well under the 100 req/day free cap) before writing any parsing code against it,
per this project's own "don't guess schemas" rule — record whatever the real shape
turns out to be in `pipelines/news/NOTES.md`, including any deviation from the
above.

## Field mapping to the shared news-client output shape
`newsapi_client.py::NewsAPIClient.search(query, page_size=100) -> pd.DataFrame` must
return the same five columns `client.py`/`guardian_client.py` already share (url,
title, seendate, domain, language, sourcecountry), so `articles_to_events` needs no
changes:
- `url` ← `articles[].url`
- `title` ← `articles[].title`
- `seendate` ← `articles[].publishedAt` — real ISO 8601
  (`2026-09-03T12:00:00Z`), parseable directly by `pd.to_datetime` with no explicit
  `format=` needed (unlike GDELT's compact `%Y%m%dT%H%M%SZ`, which does need one —
  confirm this simpler parse actually works against a real response before assuming
  it).
- `domain` ← `articles[].source.name`
- `language` — NewsAPI's `/everything` endpoint does not return a per-article
  language field. Default to `"unknown"` unless the manual-search UI's own query
  happened to be run with an (unset, per above) `language` filter — in practice this
  means every NewsAPI-sourced row's `language` column is `"unknown"` for now. This is
  an accepted, documented gap, not a bug: it only means the translate button no-ops
  for NewsAPI-sourced rows (matching how it already correctly no-ops for the ~1000
  pre-`language`-schema GDELT/Guardian rows already in the lake) rather than
  guessing a language.
- `sourcecountry` — no equivalent field exists in the response at all. Leave as an
  empty string, consistent with how `geo` already resolves primarily via headline
  keywords (`tagging.py::extract_geo`) rather than the publisher-country fallback.

## Design: manual, on-demand only — not a `pull_*.py` entrypoint
`pipelines/news/pull_news.py` gains:
```python
def manual_newsapi_search(
    client: NewsAPIClient, query: str, commodity: str
) -> pd.DataFrame:
    """Never called from main() -- see this file's own module docstring and
    specs/16_newsapi-supplement.md for why NewsAPI stays out of the scheduled pull."""
    articles = client.search(query)
    if articles.empty:
        return articles
    return articles_to_events(articles, commodity, event_type="manual_search", source="newsapi")
```
Page `09_events.py` gains an `st.expander("Search NewsAPI (manual — not a scheduled
source)")`, placed directly below the existing commodity/tag/severity filter row and
above the news map, containing: a text input for the query, a commodity selectbox
(reusing the same commodity options already used elsewhere on the page), and a
"Search" button. On click: call `manual_newsapi_search(...)`, then
`core.storage.write_events(result, source="newsapi")` if non-empty, then `st.rerun()`
so the fresh rows immediately appear in the map/feed/table below. A `st.caption`
under the button states plainly: *"One-off manual pull — NewsAPI is not part of the
scheduled news ingestion (see pipelines/news/NOTES.md)."*

## Session (weekday, 1 h)
> Read NOTES.md, specs/09_news-events.md, specs/16_newsapi-supplement.md. Confirm
> the real `/v2/everything` response shape live with one call (respect the 100
> req/day cap). Build `newsapi_client.py` behind the shared interface;
> `manual_newsapi_search` in `pull_news.py`; wire the manual-search expander into
> page 09. Add NewsAPI's real key param name to `tests/conftest.py`'s
> `filter_query_parameters`. Cassette test for the client; a test asserting
> `pull_news.py::main`'s own source contains no `NewsAPIClient` reference (a real
> regression guard, not just a docstring promise). Acceptance: a real manual search
> for a real query returns tagged rows in the lake via the existing tagging
> pipeline; `pull_news.py` itself is otherwise untouched and still contains no
> NewsAPI call.

## Definition of Done
- Manual search control live on page 09, writes real rows via the existing
  tagging/dedup pipeline.
- Zero NewsAPI calls from any scheduled entrypoint — `pull_news.py::main` reviewed
  and confirmed clean, plus the regression test above.
- Tests green, ruff/mypy clean, no secret in any committed cassette.

## Stretch
- If the operator upgrades to a paid NewsAPI plan, add it to `pull_news.py::main()`
  alongside GDELT/Guardian, following the exact same per-source resilience pattern
  those two already use — record that decision here first.
