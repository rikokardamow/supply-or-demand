# Spec 16 — NewsAPI Supplement & Adanos Market-Sentiment Overlay

**Est. 2–3 h · Prereq: Spec 00; Spec 09 (news pipeline) for the NewsAPI half.
Independent data sources — NewsAPI extends the existing news pipeline, Adanos is a
new small pipeline.**

## Objective & alpha question
Two independent, small additions: (1) NewsAPI.org as a third general-news source
alongside GDELT/Guardian, subject to the same real ToS limit Spec 09 already found and
deliberately left unscheduled; (2) Adanos's Reddit/X/News/Polymarket buzz and
sentiment scores for a small curated set of energy-sector tickers, as a market-attention
overlay — question: *does retail/social attention on energy equities lead or merely
echo what the physical fundamentals (stocks, flows, cracks) are already showing?*

## Part A — NewsAPI.org (extends `pipelines/news/`)

### The real constraint, already found once in this project — do not re-litigate it
Spec 09's own Definition of Done says, verbatim: **"NewsAPI absent from scheduled
pulls."** Its free Developer tier's terms are dev/testing only — **not licensed for
production use** — capped at 100 req/day with a 24-hour publish delay on articles.
This dashboard's standard pattern (`pull_daily.py`/`pull_weekly.py` run on a schedule,
per Spec 13) *is* production use of the data once it's live. **Do not wire NewsAPI
into `pull_news.py`'s scheduled entrypoint.** A real key now exists in `.env`
(`settings.newsapi_key`, already a field) — that only means local/manual experimentation
is available, not that the ToS constraint has changed. Before this source can ever
join the scheduled pull, the operator must explicitly upgrade to a paid NewsAPI plan;
record that decision here (or in the README) if it ever happens, rather than silently
starting to schedule it.

### Design: manual, on-demand only — not a `pull_*.py` entrypoint
`pipelines/news/newsapi_client.py`, same interface as `client.py`/`guardian_client.py`
(`.search(query, page_size) -> pd.DataFrame` with the shared columns: url, title,
seendate, domain, language, sourcecountry). Real `/v2/everything` response shape
(`{status, totalResults, articles: [{source:{id,name}, author, title, description,
url, urlToImage, publishedAt, content}]}`) needs live confirmation at implementation
time before mapping fields — do not assume the field names above are exact.

Exposed only via a manual "Search NewsAPI" control on page `09_events.py` (a text
input + button, calling the client directly and running it through the existing
`tagging.py`/`articles_to_events` path before `write_events`) — a human-triggered,
one-off call each time, not a background job. This keeps real daily volume far under
the 100 req/day free cap and keeps the dashboard's own scheduled pulls (the part that
would actually constitute "production use" of the data) NewsAPI-free, matching Spec
09's existing Definition of Done rather than quietly reopening it.

### Session (weekday, 1 h)
> Read CLAUDE.md, specs/09_news-events.md, specs/16_newsapi-adanos-sentiment.md.
> Confirm the real `/v2/everything` response shape live (a single manual call is
> enough — respect the 100 req/day cap). Build `newsapi_client.py` behind the shared
> interface; wire the manual search control into page 09. Cassette test with the key
> filtered (`filter_query_parameters` already covers `api-key`/`api_key` conventions —
> confirm NewsAPI's actual param name, likely `apiKey`, and add it if not already
> covered). Acceptance: a manual search for a real query returns tagged rows in the
> lake via the existing tagging pipeline; `pull_news.py` itself is untouched and still
> contains no NewsAPI call.

## Part B — Adanos Market-Sentiment Overlay (new `pipelines/adanos/`)

### What Adanos is, and the real limits on the free tier
A commercial API (`api.adanos.org`) giving buzz/attention and sentiment scores for
stock tickers across four independent platform perspectives (Reddit, X/Twitter, News,
Polymarket prediction markets) plus a separate Reddit crypto product. Confirmed from
the vendor's own published API reference: **Free tier — 250 requests/month total,
30-day historical lookback, 100 req/min burst cap, no commercial-use licence, no raw
mentions or text-sentiment endpoints.** A real key now exists in `.env`
(`settings.adanos_api_key`) but the 250 req/month ceiling is the hard design
constraint for everything below — this is not a source to poll daily per ticker.

**Verify live at implementation time, do not assume from the vendor's docs alone**:
exact current field names/response shape for `/compare` and `/trending/sectors`
(the docs above are the vendor's own reference as pasted into this project — treat
them as a starting point, not confirmed-live, per this project's "don't guess
schemas" rule); whether `X-RateLimit-Remaining-Monthly` response headers are reliable
enough to self-throttle against, so a bug can't silently burn the whole monthly quota
in one run.

### Curated ticker universe (energy-sector only — not the full 35,000-ticker universe)
A small, hand-maintained list in `pipelines/adanos/tickers.py`: energy majors (XOM,
CVX, COP, SLB, OXY, BP, SHEL) and energy-sector ETFs (XLE, USO, UNG, XOP). Confirm each
symbol is actually recognised by Adanos's `/search` endpoint before relying on it in
`/compare` (the search endpoint's own response includes a `summary` block that doubles
as a cheap existence check). Compare supports up to 10 tickers per call — this list
fits in one call per platform.

### Budget: stay far under 250 req/month
One `/compare` call per platform (Reddit, X, News, Polymarket — 4 calls) plus one
`/trending/sectors` call (Reddit only, filtered to Energy in code since the endpoint
doesn't take a sector filter) per **week** = 5 calls/week ≈ 22 calls/month, leaving
generous headroom for manual `/search`/exploration calls and the free monthly reset
being anchored to key-creation date rather than calendar month (per the vendor's own
documented quota-reset behaviour). Do not add the Reddit-crypto product, the
sentiment-analysis POST endpoint (Professional-only), or per-ticker `/mentions` (also
Professional-only) — out of scope and outside the free tier regardless.

### Data model — fits the existing `ts_long` schema, no new schema needed
Per ticker × platform × date: `series_id = adanos.{platform}.{ticker_lower}.buzz_score`
and `adanos.{platform}.{ticker_lower}.sentiment_score` (two series per ticker per
platform), `source="adanos"`, `unit="score_0_100"` for buzz / `"score_-1_1"` for
sentiment, `geo="US"` (all curated tickers are US-listed), `freq="daily"`. Sector
trend goes to `adanos.reddit.sector_energy.buzz_score`.

### Visualisation spec (extends page `10_macro.py`, does not need a new page)
A small "Energy-sector sentiment" section: (1) a compact multi-line buzz-score panel,
one line per platform, for the curated ticker basket's mean; (2) a bar comparing each
ticker's latest sentiment_score across the four platforms (grouped bar, house
colours); (3) the sector-level buzz trend line. Frame explicitly as attention/flow
data, not a trading signal — caption language should mirror Spec 14's own honesty
rules (§0.6): this measures how much people are talking and how they feel, not
whether they're right.

### Claude Code session (weekday, 1.5–2 h)
> Read CLAUDE.md, specs/16_newsapi-adanos-sentiment.md. Confirm live: `/search` for
> each curated ticker resolves; `/compare` response shape for one platform. Build
> `pipelines/adanos/client.py` (thin wrapper, one method per used endpoint),
> `tickers.py`, `pull_adanos.py` (weekly entrypoint — respect the request budget
> above, log the `X-RateLimit-Remaining-Monthly` header after each call rather than
> discarding it). Cassette tests (filter `X-API-Key`). Wire the three visuals into
> page 10. Acceptance: a real weekly pull writes ts_long rows for all four platforms
> without exceeding the documented request budget; `X-RateLimit-Remaining-Monthly`
> logged and sane after the run.

## Definition of Done
- NewsAPI: manual search control live on page 09; zero calls from any scheduled
  entrypoint (grep `pull_news.py`/`pull_daily.py` for confirmation, same as Spec 09's
  own acceptance bar).
- Adanos: weekly pull for the curated energy-ticker basket + Reddit energy-sector
  trend, writing `ts_long`; three visuals live on page 10; real request count for a
  full weekly run documented in `pipelines/adanos/CLAUDE.md` and confirmed under
  the free-tier monthly budget. Tests green.

## Stretch
- Adanos: once/if a paid tier is ever purchased, add the `/mentions` raw-mention
  endpoints and cross-reference sentiment spikes against the existing GDELT/Guardian
  event log (Spec 09) for the same tickers' underlying commodity.
- NewsAPI: if the operator upgrades to a paid plan, revisit scheduling it properly
  alongside GDELT/Guardian rather than as a manual-only control.
