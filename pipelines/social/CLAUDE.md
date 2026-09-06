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
Upstream's public fetchers return prompt-ready prose and its typed layer is
underscore-private, so the request handling is adapted rather than imported.

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
