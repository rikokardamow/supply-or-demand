# pipelines/social — Claude Code Guide

## Real API shapes, confirmed live (not just read from upstream source)

**Reddit RSS search** (`https://www.reddit.com/r/energy/search.rss?q=Henry+Hub&restrict_sr=on&sort=new&limit=25`,
`User-Agent: energy-dashboard/0.1 (Kardamow research dashboard)`): **13 entries** came
back for a `limit=25` request (fewer matching posts exist, not a truncation bug). Each
`atom:entry` carries `author`, `category`, `content`, `id`, `link`, `updated`,
`published`, `title`, and — only on posts with a preview image — `thumbnail`. Confirmed
present beyond the brief's expected set: `category` (`{"term": "energy", "label":
"r/energy"}`) and `published` (duplicates `updated` on every entry seen). **Confirmed
absent: no score field and no comment-count field anywhere on the entry** — the
`content` field's HTML embeds a `[comments]` link but never a count.

**Critical, confirmed-live gotcha: Reddit's unauthenticated RSS rate limit is one
request per ~60 seconds, not a generous budget.** The first request returned
`X-Ratelimit-Remaining: 0.0`, `X-Ratelimit-Used: 1`, `X-Ratelimit-Reset: 45` (seconds) —
i.e. the quota was already exhausted by that single call. A second identical request
made 2 seconds later returned **HTTP 429**. Task 3's pull design must space Reddit
calls at least ~60 seconds apart (or honour `X-Ratelimit-Reset`), not batch them.

**Polymarket** (`https://gamma-api.polymarket.com/events?limit=5&active=true`, no
auth): bare **JSON array** of event objects (not wrapped). Real field names: `id`
(**string**, e.g. `"2890"` — not an int), `title`, `slug` (used to build
`https://polymarket.com/event/<slug>` — there is no separate `url` field),
`createdAt` / `updatedAt` / `startDate` / `endDate` / `closedTime` (multiple ISO-8601
timestamp fields, no single canonical "timestamp"), and a top-level `commentCount`
(present and populated — e.g. `8126` on one event; Polymarket, unlike Reddit, does
carry a real comment count). Each event embeds a nested `markets` array; each market
carries its own much larger field set including `outcomes`, `outcomePrices`,
`bestBid`/`bestAsk`, `volume`, `liquidity`. No auth required; no rate-limit headers
were observed on any response.

**Critical, confirmed-live gotcha: Polymarket's `q` and `search` query parameters are
silently ignored.** `?q=energy`, `?search=energy`, and even `?q=zzznonsensequery9999`
all returned the identical default/unfiltered event list (same three events, same
order, regardless of query string) with HTTP 200 — no error, no indication the
parameter did nothing. **The real, working filter is `tag_slug`**: `?tag_slug=energy`
returned a genuinely different, energy-relevant set (`US x Iran ceasefire before Oil
hits $120?`, `Will there be a power grid emergency before October 1?`, `Will Saudi
Arabia boost oil production in Q4?`). Task 3 must filter Polymarket by `tag_slug`, not
by a keyword-search parameter guessed from general REST convention.

**StockTwits** (`https://api.stocktwits.com/api/2/streams/symbol/XOM.json`, no auth):
**wrapped JSON object** with top-level keys `symbol`, `cursor`, `regions`, `filters`,
`messages`, `response` (`response` is just `{"status": 200}` — not where errors are
reported; HTTP status itself is authoritative). `messages` is a list of 30 items. Real
message field names: `id` (**int**), `body` (plain text with `$XOM`-style cashtags
inline), `created_at` (ISO-8601), `entities.sentiment` (either `null` or
`{"basic": "Bullish"}` / `{"basic": "Bearish"}` — StockTwits' own user-tagged
sentiment, present on roughly a third of messages in the sample, **absent — not
zero — on the rest**), `likes` (either `null` or `{"total": N, "user_ids": [...]}`),
`links` (either `null` or a list of link-preview objects, each with its own `url`
and `created_at`), and `symbols` (list, each with `symbol`, `exchange`, `title`).
There is no direct permalink field on the message itself; a URL would have to be
constructed from `user.username` + `id` if ever needed. No auth was required and no
`X-RateLimit-*` response headers were present on any of five consecutive calls.

**Confirmed-live gotcha, StockTwits: transient, unexplained 403.** One probe run in
this session's sequence returned a single **HTTP 403 Forbidden** with an empty body
sandwiched between otherwise-successful 200s (before and after, including five
back-to-back retries afterwards that all succeeded). No `Retry-After` or rate-limit
header was present on the 403 to explain it. Treat this as a real, if rare and
unexplained, failure mode — Task 3's fetch should tolerate one non-2xx response and
retry, not treat a single 403 as proof StockTwits is blocking us.

## Provenance
Fetch logic adapted from TauricResearch/TradingAgents (Apache-2.0), commit
`9dee508c44662702281a8dbaad1f7b42179b5ba7` (`main`, dated 2026-09-01, merge of
"Post-v0.4.0 fixes: FRED vintage, Reddit 429, debate neutrality, feed bound" —
upstream's own history independently confirms the Reddit 429 behaviour found above).
Confirmed by reading `tradingagents/dataflows/reddit.py` at that pinned commit
(fetched directly from GitHub, not re-derived from documentation): the public
`fetch_reddit_posts(ticker, subreddits=..., limit_per_sub=5, ...) -> str` returns a
single formatted plaintext block (its own module docstring states the return is
"formatted plaintext blocks ready for prompt injection"), built by joining per-post
blocks with `"\n\n".join(blocks)`. All of the actual request/parsing logic sits
behind underscore-private functions — `_fetch_subreddit(...) -> list[dict]`,
`_fetch_subreddit_rss(...) -> list[dict]`, `_fetch_subreddit_json(...) -> list[dict]`
— none of which are part of the public API. This is why the request handling in
this pipeline is adapted rather than imported: there is no public function that
returns structured rows, only prompt-ready prose. Two more things confirmed live in
that same file, independently corroborating findings above rather than merely
matching them: `_fetch_subreddit_rss`'s own docstring says "Carries no score /
comment counts, so those fields are left None" (matches this pipeline's own
no-score/no-comment-count finding), and it already implements a 429 back-off
honouring `Retry-After` before giving up (matches the Reddit rate-limit gotcha
found independently above) — plus a detail this session's probes did not test:
Reddit's richer JSON search endpoint being WAF-blocked, tracked as issue #862.
Two separate docstrings describe this, worded differently and not
interchangeable: the module docstring says the endpoint "is reliably
WAF-blocked (`HTTP 403`) for public clients (issue #862)", while
`_fetch_subreddit_json`'s own docstring separately says "Reddit's WAF currently
returns `403 Blocked` on this endpoint for non-OAuth clients (issue #862)" —
either way, that is why upstream defaults to RSS.

Attribution recorded verbatim in the repo-root `NOTICE` file:

> This product includes software adapted from TradingAgents
> (https://github.com/TauricResearch/TradingAgents), Copyright TauricResearch,
> licensed under the Apache License, Version 2.0. The social fetch logic in
> pipelines/social/client.py is derived from its tradingagents/dataflows/
> modules.

## Confirmed constraint: RSS carries no score and no comment count
Post metrics are written as missing, never as 0. A fabricated zero would be
indistinguishable from a real zero — the same failure mode Spec 17 caught in
Adanos's zeroed rows for unrecognised tickers.

## Queries that returned nothing
No probed query returned zero rows in this session — Reddit returned 13/25 requested,
Polymarket's default and `tag_slug=energy` listings both returned rows, and StockTwits
returned a full 30-message page for `XOM`. This is a smaller ticker/query set than
Set B will eventually cover; Task 3's own pull is expected to surface genuine
zero-row queries (thinly-traded tickers, narrow keyword searches) the way Adanos's
OPEC/OPEC+ tickers did — that will be a finding for Task 3, not evidence of a bug here.

## Task 1: the frozen twelve tickers (`pipelines/social/queries.py`)
Ranked 2026-09-06 by mean `adanos.reddit.<ticker>.buzz_score`, taken directly off
`pipelines/adanos/tickers.py`'s 57-ticker universe. The basis is honestly narrow:
this is **not** "over the Adanos history" — there is no history yet. It is the
single day of Adanos data present in the lake, all timestamped 2026-09-03 (one
pull, 57 rows total). Of those 57 tickers, 45 had nonzero buzz on that day, so the
ranking was genuinely differentiated rather than noise, but it is still a one-day
snapshot and will not be recomputed as more days accumulate — the set is frozen
per Spec 29 because series IDs built from it are permanent.

The chosen twelve, in the order the ranking produced them (highest mean
`buzz_score` first):

```
CVX, XOM, USO, BP, CCJ, XLE, COP, SU, SLB, PBR, NEE, CNQ
```

Full one-day ranking as observed (mean `buzz_score` on 2026-09-03; all 57 tickers,
descending): CVX 66.8, XOM 64.4, USO 55.2, BP 49.7, CCJ 47.2, XLE 45.0, COP 41.8,
SU 38.0, SLB 36.3, PBR 35.7, NEE 35.0, CNQ 34.7, FSLR 34.4, ENPH 32.9, OXY 30.8,
EQT 29.0, PSX 27.3, VLO 26.8, TAN 26.6, EPD 26.0, AMLP 25.5, OKE 25.3, NOV 25.1,
UEC 25.0, UUUU 25.0, MPC 24.9, ET 24.1, TTE 23.1, HAL 22.9, CVE 22.7, EOG 22.7,
XOP 22.3, BKR 20.9, UNG 19.8, E 19.4, VDE 18.2, EQNR 16.9, FANG 16.7, SHEL 16.6,
WDS 15.1, URA 14.1, BEP 13.9, PBF 13.1, IXC 13.0, LNG 12.4, then 12 tickers at
exactly 0.0 buzz (AR, ARADEL, DVN, BTU, GKP, GENL, SEPLAT, OANDO, ICLN, OIH, KMI,
WMB).

Note the frozen twelve include index/ETF and non-US tickers (USO, XLE, BP, CCJ,
SU, PBR, CNQ) alongside the US majors — this reflects Reddit buzz on 2026-09-03
as actually observed, not a curated "energy majors" shortlist. `SUBREDDITS` is
deliberately not defined in `queries.py`: Reddit's fetch strategy (subreddit list
vs. one site-wide request per subject) is Task 2's decision, gated on whether
site-wide search works within the ~60-second rate limit recorded above.
