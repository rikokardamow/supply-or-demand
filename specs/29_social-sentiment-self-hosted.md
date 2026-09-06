# Spec 29 — Self-Hosted Social Sentiment (Reddit / Polymarket / StockTwits)

**Est. 3–4 h · Prereq: Spec 00, Spec 17 (built). Independent — new `pipelines/social/`,
new `core/sentiment.py`, extends the existing Adanos section on page `10_macro.py`.
No new schema. Spec 17 and `pipelines/adanos/` are not edited.**

## Objective & alpha question
Fetch raw social and prediction-market posts directly, score them in-repo, and show the
result **beside** Adanos's vendor-scored sentiment with the deviation between them.
Question: *where the two disagree, which one is telling the truth — and does either lead
the physical fundamentals this dashboard already tracks?* Framed throughout as
attention/flow data, never as a trading signal (Spec 17's Honesty rule carries over
verbatim and applies to every series added here).

## Why this exists alongside Adanos, not instead of it
`pipelines/adanos/CLAUDE.md` records a real, live-confirmed coverage gap: the five
OPEC/OPEC+ geographic-exposure tickers added on explicit request are **recognised but
empty**. `GKP`, `SEPLAT`, `OANDO`, `ARADEL` all returned `buzz_score: 0.0` and
`sentiment_score: null` across Reddit; `GENL` had exactly one News mention. Adanos is a
US-retail-sentiment product and those are LSE/NGX listings.

The decisive difference is not price: **self-hosted fetchers search by query, not by
ticker.** They can cover "Kurdistan oil exports", "NNPC", "Urals discount", "JKM",
"Henry Hub", "Strait of Hormuz" — commodity and geopolitical topics a ticker basket
structurally cannot express. This is a second axis of coverage, not a cheaper Adanos.

Adanos is retained because it supplies something this spec deliberately does not
attempt: a vendor-scored sentiment number with consistent methodology across four
platforms, and it remains the better instrument for the US-listed majority of the
57-ticker basket. Keeping both is what makes the deviation meaningful.

## Provenance and licence
The fetch logic is adapted from `TauricResearch/TradingAgents` (Apache-2.0):
`tradingagents/dataflows/{reddit,polymarket,stocktwits}.py`. The repo is **not** added as
a dependency — its public fetchers return prompt-ready prose
(`fetch_reddit_posts(...) -> str`, ending in a joined text blob), while its typed layer
(`_fetch_subreddit(...) -> list[dict]`) is underscore-private and would break on any
upstream release. We take the request-handling logic and emit canonical rows. Record the
upstream commit SHA adapted from, and the Apache-2.0 attribution, in
`pipelines/social/CLAUDE.md` and `NOTICE`.

## Real API shape — one confirmed constraint, the rest to be verified live
**Confirmed by reading the upstream source** (not yet by our own calls):

- **Reddit needs no API key.** The default path is the public Atom/RSS search feed
  `https://www.reddit.com/r/{sub}/search.rss`. The richer `/search.json` endpoint is
  **reliably WAF-blocked (HTTP 403)** for public clients (upstream issue #862), and
  probing it on every call doubled request volume and tripped `429` on the RSS fallback.
  Keep a JSON path in code, do not use it by default.
- **RSS carries no score and no comment count.** This is the single most important
  constraint in this spec. Our buzz metric therefore **cannot** be score- or
  upvote-weighted; it is a post-count measure. Posts arriving without metrics are marked
  as such and the metrics omitted — never written as zero, which would be
  indistinguishable from a real zero. This is the same failure mode Spec 17 caught in
  Adanos (`buzz_score: 0.0` for an unrecognised ticker) and it is caught the same way.
- On `429`, back off once honouring `Retry-After`. Send a descriptive, identified
  `User-Agent` per Reddit's API etiquette.

**Not yet verified and must be, as the mandatory first implementation step** (the same
discipline Spec 17 applied to its 57 tickers, which caught the real `SEPL` → `SEPLAT`
error): the live field shape of Polymarket and StockTwits, whether either needs a key,
their real rate limits, and whether any query below returns usable volume. Record the
real outcome — including queries that return nothing — in `pipelines/social/CLAUDE.md`.
Do not write pull code against an unverified field shape.

## The query universe — topics, not tickers
Two deliberately separate sets, because they answer different questions.

**Set A — comparison overlap (ticker queries).** Twelve US-listed tickers already in
`pipelines/adanos/tickers.py`, queried by symbol. These exist *solely* so there is an
apples-to-apples series against Adanos for the same ticker, platform and day. This is
the set that feeds the deviation panel.

The twelve are chosen once, at implementation time, by ranking mean
`adanos.reddit.{ticker}.buzz_score` over the Adanos history already in the lake and
taking the top twelve — the same ranking `10_macro.py` already uses for
`_TOP_N_TICKERS_FOR_SENTIMENT_BAR`. The resulting list is then **frozen as a constant**
in `queries.py` and the ranking is not recomputed on later runs; a set that silently
re-ranks would break the continuity of every `social.*` series it names. Record the
chosen twelve and the date ranked in `pipelines/social/CLAUDE.md`.

**Set B — commodity and geopolitical topics.** The coverage Adanos cannot express:

| Theme | Queries |
|---|---|
| Crude benchmarks & differentials | Brent, WTI, Urals discount, Dubai swap |
| Gas / LNG | Henry Hub, JKM, TTF, LNG cargo |
| Chokepoints & geopolitics | Strait of Hormuz, Red Sea shipping, Bab el-Mandeb |
| OPEC+ producers (the Adanos gap) | NNPC, Kurdistan oil exports, Libya NOC, PDVSA |
| Refining | crack spread, refinery outage |

Set B has **no Adanos counterpart by construction** and therefore never appears in the
deviation panel — it stands alone as attention data. Subreddits to search are a config
constant in `pipelines/social/queries.py`, following `pipelines/news/queries.py`.

Expect much of Set B to return little or nothing on Reddit. That is a real finding, not
a bug, and is recorded rather than worked around — exactly as Spec 17 recorded the
near-zero OPEC+ ticker buzz.

## Data model — no new schema
Both existing schemas are sufficient; `core/schemas.py` is not touched.

**Raw posts → `events`.** `event_id = sha256(url)` (matching
`pipelines/news/events.py::_event_id`, so `write_events`' dedup works unchanged),
`source="reddit"` / `"polymarket"` / `"stocktwits"`, `headline` = post title, `commodity`
and `geo` derived by reusing `pipelines/news/tagging.py` rather than a second tagger,
`tags` carrying the query that matched, `severity=1` fixed (these are posts, not events
with intensity), `language="en"`.

**Scores → `ts_long`.** `series_id = social.{platform}.{subject}.{metric}` where
`subject` is the lower-cased ticker (Set A) or a slugged topic (Set B), and `metric` is
`post_count` or `sentiment_score` — e.g. `social.reddit.xom.post_count`,
`social.reddit.strait_of_hormuz.sentiment_score`. `source` = the platform,
`unit="count"` / `"score_neg1_to_1"`, `freq="D"`.

Series IDs are permanent, so the topic slug rule is fixed here rather than left to the
implementation: lower-case, then every run of non-alphanumeric characters becomes a
single underscore, then strip leading and trailing underscores — "Strait of Hormuz" →
`strait_of_hormuz`, "Bab el-Mandeb" → `bab_el_mandeb`. The slug is computed once when a
query is added to `queries.py` and stored beside its query string, never re-derived at
write time; changing a query's display text must not silently orphan its history.

The `social.*` namespace and the distinct `source` value keep these permanently separable
from Spec 17's `adanos.*` series. **The two are never blended into a single number.** Note
the deliberate asymmetry: ours is `post_count`, Adanos's is `buzz_score` (0–100). They are
not the same quantity and are not compared directly — only the two `sentiment_score`
series are, both being on −1..+1.

## Scoring — deterministic first, by decision
Raw posts arrive as text and something must score them. This spec uses a **deterministic
lexicon scorer** (VADER-class) as the only scorer in scope.

**Why, explicitly:** the project's test story is vcrpy cassettes and
`00_TRADING_CONVENTIONS.md` requires a model card with window / refit / OOS status for
anything estimated. A lexicon scorer is reproducible, free, offline, and fully
cassette-testable — the same text always yields the same score, so a regression is a real
regression. An LLM scorer would score better and quietly cost reproducibility, which is
the wrong trade for a series whose whole purpose is to be compared against a vendor.

LLM scoring via the existing `anthropic` dependency is **explicitly out of scope here**
and deferred to its own spec, where it would land as a third, separately-named series
(`social_llm.*`) with a pinned model ID and its own model card — never as a silent
upgrade to `social.*`.

**Dependency ask (root CLAUDE.md rule 7):** this needs one new dependency,
`vaderSentiment` (or equivalent lexicon scorer). Confirm before adding, and record the
justification in `pyproject.toml` in the style already used for `statsmodels`/`arch`.
Note the honest limitation in `pipelines/social/CLAUDE.md`: VADER is calibrated on
general social-media English, not energy-trading jargon. "Crude tanking" is bearish price
language, not negative sentiment about crude. Do not present the scores as better than
they are.

## Reconciliation — `core/sentiment.py`
Analytics live in flat `core/<topic>.py` modules per the root guide. This module holds
the entire both-sources comparison and is the only place the two namespaces meet.

- `overlap_frame(ticker, platform) -> pd.DataFrame` — joins
  `adanos.{platform}.{t}.sentiment_score` and `social.{platform}.{t}.sentiment_score` on
  `ts`, inner join only. Days where either side is missing are dropped and **counted**,
  and the count is surfaced in the UI: a deviation computed over 3 overlapping days is
  not a finding.
- `deviation(frame) -> pd.DataFrame` — signed difference (`social − adanos`), plus rolling
  correlation over a stated window and the agreement rate on sign.
- No blending, no weighted average, no "consensus" series. The two numbers and their gap
  are the output. This follows the established convention that published benchmarks are
  shown beside repo estimates with the deviation, never merged.

## Pipeline structure — matches the house pattern
`pipelines/social/`: `CLAUDE.md`, `client.py` (the three fetchers, typed `list[dict]`
returns), `queries.py` (Sets A and B), `score.py` (lexicon scoring), `events.py` (posts →
`events`, reusing `pipelines/news/tagging.py`), `pull_social.py` (orchestration,
per-platform `requests.exceptions.RequestException` resilience so one platform failing
never aborts the others — the pattern `pipelines/macro/pull_macro.py` established and
Spec 17 reused), and `pull_weekly.py` as a thin re-export of `pull_social.main`.

Register as `("social", "pipelines.social.pull_weekly")` in `infra/run_scheduled.py`'s
`weekly_fri` group, beside `adanos` — same cadence, so the overlap join has matching dates
rather than a systematic one-day offset that would masquerade as deviation.

## Visualisation — extends page `10_macro.py`, no new page
A new subheader "Self-hosted social sentiment" below the existing Adanos section, three
`card(...)`-wrapped charts in Kardamow house style:

1. **Adanos vs self-hosted, one ticker** — two lines (navy = Adanos, light blue =
   self-hosted), overlap-day count annotated near the last point.
2. **Deviation** — signed gap over time, red accents where the two disagree on sign.
3. **Topic attention (Set B)** — post counts for the commodity/geopolitical queries, with
   an explicit caption that these have no Adanos counterpart and are attention only.

Empty states follow the existing precedent: `st.info("No social data yet — run
pipelines/social/pull_social.py.")`.

## Acceptance criteria
- Live verification done **before** pull code, real outcomes (including empty queries)
  recorded in `pipelines/social/CLAUDE.md`.
- Cassette tests for all three fetchers; a resilience test proving one platform's
  `RequestException` does not abort the others (mirrors `test_adanos_pull.py`).
- A test proving RSS posts with no score/comment count are written as **missing**, not as
  `0` — the Spec 17 zeroed-row lesson, enforced.
- A `core/sentiment.py` test on a fixed frame proving the deviation is signed correctly
  and that dropped non-overlapping days are counted.
- `pipelines/adanos/`, `specs/17_adanos-sentiment-overlay.md`, and `core/schemas.py` are
  **unchanged** — verified by diff.
- Session ends green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

## Out of scope, deliberately
LLM-based scoring (own spec, own series, own model card). Any trade signal derived from
these series. X/Twitter — Adanos already covers it and there is no free self-hosted path
worth the maintenance. Backfill: these are forward-collecting series; history starts the
day the pipeline first runs, and the UI says so.
