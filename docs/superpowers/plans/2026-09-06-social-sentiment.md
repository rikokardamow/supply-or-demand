# Self-Hosted Social Sentiment (Spec 29) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch raw Reddit/Polymarket/StockTwits posts without a vendor, score them in-repo with a deterministic lexicon scorer, and display them beside Spec 17's Adanos series with the signed deviation.

**Architecture:** A new `pipelines/social/` follows the established pipeline shape (client → transform → `pull_*.py` entrypoint → thin `pull_weekly.py` re-export). Posts land in the existing `events` schema; daily aggregates land in `ts_long` under a `social.*` namespace kept permanently separate from `adanos.*`. A new flat `core/sentiment.py` holds the entire two-source reconciliation and is the only place the namespaces meet. Page `10_macro.py` gains one new subheader below its existing Adanos section.

**Tech Stack:** Python 3.12, pandas, requests, pyarrow/DuckDB via `core.storage`, plotly + streamlit, `vaderSentiment` (new — see Global Constraints). Tests: pytest + vcrpy cassettes.

**Spec:** `specs/29_social-sentiment-self-hosted.md`

## Global Constraints

Copied verbatim from the spec and the root `CLAUDE.md`. Every task's requirements implicitly include this section.

- **Never blend the two sources into a single number.** `adanos.*` and `social.*` stay separate series; the deviation is the output, not a consensus.
- **Never write a missing metric as `0`.** RSS posts carry no score/comment count. Absent metrics are `None`, never `0` — a fabricated zero is indistinguishable from a real zero. This is the Spec 17 zeroed-row lesson.
- **`pipelines/adanos/`, `specs/17_adanos-sentiment-overlay.md` and `core/schemas.py` are unchanged.** Verified by diff at the end. No new schema.
- **Series ID grammar:** `social.{platform}.{subject}.{metric}`, lower-case, where `metric` ∈ {`post_count`, `sentiment_score`}. `unit="count"` or `"score_neg1_to_1"`. `freq="D"`. `source` = the platform name.
- **Topic slug rule (fixed, permanent):** lower-case → every run of non-alphanumeric characters becomes a single `_` → strip leading/trailing `_`. Computed once when a query is added and stored beside its query string; never re-derived at write time.
- **The twelve Set A tickers are frozen once** at Task 1 and never re-ranked.
- Secrets only via `core.settings`. Never printed, logged, or committed.
- Pipelines write the lake; pages read the lake. Pages never call external APIs.
- British English in all prose, labels and docstrings. Charts use `core.theme`.
- Every pipeline gets a vcrpy cassette test. CI never hits live APIs.
- All modules start with `from __future__ import annotations`. Typed functions throughout.
- Session ends green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

---

### Task 0: Live verification before any pull code

The spec makes this mandatory and it is not ceremony — the identical step in Spec 17 caught a real error (`SEPL` was wrong; the real Adanos symbol is `SEPLAT`). Write no pull code until this task's findings are recorded.

**Files:**
- Create: `pipelines/social/__init__.py` (empty)
- Create: `pipelines/social/CLAUDE.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the recorded real field shapes that Tasks 2 and 3 code against.

- [ ] **Step 1: Create the package directory and empty `__init__.py`**

```bash
mkdir -p pipelines/social
touch pipelines/social/__init__.py
```

- [ ] **Step 2: Probe Reddit's RSS search feed live**

Run this throwaway probe (do not commit it):

```python
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

UA = "energy-dashboard/0.1 (Kardamow research dashboard)"
qs = urlencode({"q": "Henry Hub", "restrict_sr": "on", "sort": "new", "limit": 25})
url = f"https://www.reddit.com/r/energy/search.rss?{qs}"
raw = urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read()
root = ET.fromstring(raw)
ns = {"atom": "http://www.w3.org/2005/Atom"}
entries = root.findall("atom:entry", ns)
print("entries:", len(entries))
for e in entries[:3]:
    print({c.tag.split('}')[1]: (c.text or c.attrib) for c in e})
```

Record: how many entries came back, the exact child tags present on an entry (expect `title`, `link`, `updated`, `id`, `author`, `content`), and confirm **no score and no comment count exist**.

- [ ] **Step 3: Probe Polymarket and StockTwits live**

```python
import json
from urllib.request import Request, urlopen

UA = "energy-dashboard/0.1 (Kardamow research dashboard)"

def probe(url: str) -> None:
    try:
        raw = urlopen(Request(url, headers={"User-Agent": UA}), timeout=30).read()
        payload = json.loads(raw)
        rows = payload if isinstance(payload, list) else payload.get("messages") or payload.get("data")
        print(url, "->", type(payload).__name__, "rows:", len(rows) if rows else 0)
        if rows:
            print(json.dumps(rows[0], indent=2)[:800])
    except Exception as exc:
        print(url, "-> FAILED", type(exc).__name__, exc)

probe("https://gamma-api.polymarket.com/events?limit=5&active=true")
probe("https://api.stocktwits.com/api/2/streams/symbol/XOM.json")
```

Record for each: whether it works unauthenticated, the real top-level shape (bare array vs wrapped object), the exact field names for id / title / timestamp / url, and any rate-limit headers. **If StockTwits returns 403/429 for unauthenticated clients, that is a real finding** — record it and mark StockTwits out of scope for Task 3 rather than inventing a workaround.

- [ ] **Step 4: Write `pipelines/social/CLAUDE.md` with the real outcomes**

Follow `pipelines/adanos/CLAUDE.md`'s style: state what was confirmed live versus what is only documented, and record failures and empty results as findings rather than omitting them. It must contain, with real values from Steps 2–3:

```markdown
# pipelines/social — Claude Code Guide

## Real API shapes, confirmed live (not just read from upstream source)
[Reddit RSS: entry count, exact child tags, confirmation that score/comment count are absent]
[Polymarket: top-level shape, field names, auth needed y/n]
[StockTwits: top-level shape, field names, auth needed y/n — or the real failure if it blocks us]

## Provenance
Fetch logic adapted from TauricResearch/TradingAgents (Apache-2.0), commit [SHA].
Upstream's public fetchers return prompt-ready prose and its typed layer is
underscore-private, so the request handling is adapted rather than imported.

## Confirmed constraint: RSS carries no score and no comment count
Post metrics are written as missing, never as 0. A fabricated zero would be
indistinguishable from a real zero — the same failure mode Spec 17 caught in
Adanos's zeroed rows for unrecognised tickers.

## Queries that returned nothing
[Real list. Expected for much of Set B. A finding, not a bug.]
```

- [ ] **Step 5: Add the Apache-2.0 attribution to `NOTICE`**

Append to the existing `NOTICE` file:

```
This product includes software adapted from TradingAgents
(https://github.com/TauricResearch/TradingAgents), Copyright TauricResearch,
licensed under the Apache License, Version 2.0. The social fetch logic in
pipelines/social/client.py is derived from its tradingagents/dataflows/
modules.
```

- [ ] **Step 6: Commit**

```bash
git add pipelines/social/__init__.py pipelines/social/CLAUDE.md NOTICE
git commit -m "docs(social): live-verified API shapes and Apache-2.0 attribution"
```

---

### Task 1: Query universe and the frozen ticker set

**Files:**
- Create: `pipelines/social/queries.py`
- Test: `tests/test_social_queries.py`

**Interfaces:**
- Consumes: Task 0's recorded findings (drop any platform that failed verification).
- Produces: `PLATFORMS: list[str]`, `SUBREDDITS: list[str]`, `TICKER_QUERIES: list[str]`, `TOPIC_QUERIES: list[TopicQuery]`, `slugify(text: str) -> str`, and the `TopicQuery` TypedDict with keys `slug`, `query`, `commodity`, `theme`.

- [ ] **Step 1: Rank the twelve tickers off the existing Adanos lake data**

Run this once and copy the printed list into the constant in Step 3. Do not put this ranking in committed code — the set is frozen, not recomputed.

```python
from core.storage import read_ts_long
from pipelines.adanos.tickers import TICKERS

ids = [f"adanos.reddit.{t.lower()}.buzz_score" for t in TICKERS]
df = read_ts_long(series_ids=ids)
top = (
    df.assign(ticker=df["series_id"].str.split(".").str[2].str.upper())
    .groupby("ticker")["value"].mean().sort_values(ascending=False).head(12)
)
print(list(top.index))
```

If the lake has no Adanos rows yet, run `python -m pipelines.adanos.pull_adanos` first. Record the chosen twelve and today's date in `pipelines/social/CLAUDE.md`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_social_queries.py
from __future__ import annotations

from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES, slugify


def test_slugify_follows_the_fixed_permanent_rule() -> None:
    assert slugify("Strait of Hormuz") == "strait_of_hormuz"
    assert slugify("Bab el-Mandeb") == "bab_el_mandeb"
    assert slugify("  Urals discount!! ") == "urals_discount"
    assert slugify("JKM") == "jkm"


def test_topic_slugs_are_stored_not_derived_and_are_unique() -> None:
    slugs = [q["slug"] for q in TOPIC_QUERIES]
    assert len(slugs) == len(set(slugs)), "series IDs are permanent; slugs must be unique"
    for q in TOPIC_QUERIES:
        assert q["slug"] == slugify(q["slug"]), "stored slug must already be canonical"


def test_ticker_set_is_frozen_at_twelve() -> None:
    assert len(TICKER_QUERIES) == 12
    assert TICKER_QUERIES == [t.upper() for t in TICKER_QUERIES]
    assert len(set(TICKER_QUERIES)) == 12
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `pytest tests/test_social_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.social.queries'`

- [ ] **Step 4: Write `pipelines/social/queries.py`**

Replace the `TICKER_QUERIES` values with the real twelve printed in Step 1.

```python
"""Query universe for Spec 29's self-hosted social sentiment.

Two deliberately separate sets. Set A (TICKER_QUERIES) exists solely to give an
apples-to-apples overlap against Spec 17's Adanos series for the same ticker,
platform and day -- it is frozen, not re-ranked, because a set that silently
re-ranks would break the continuity of every social.* series it names. Set B
(TOPIC_QUERIES) is the coverage Adanos cannot express at all: commodity and
geopolitical topics, searched by query rather than by ticker.

Same small-reference-table-as-Python precedent as pipelines/news/queries.py."""

from __future__ import annotations

import re
from typing import TypedDict


class TopicQuery(TypedDict):
    slug: str
    query: str
    commodity: str
    theme: str


PLATFORMS: list[str] = ["reddit", "polymarket", "stocktwits"]

SUBREDDITS: list[str] = ["energy", "oil", "commodities", "investing", "stocks"]

# Frozen [DATE] by mean adanos.reddit.*.buzz_score over the lake's Adanos history.
# Deliberately never recomputed -- see this package's CLAUDE.md.
TICKER_QUERIES: list[str] = [
    "XOM", "CVX", "COP", "OXY", "SLB", "VLO",
    "MPC", "PSX", "LNG", "EQT", "NEE", "FSLR",
]

TOPIC_QUERIES: list[TopicQuery] = [
    {"slug": "brent", "query": "Brent crude", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "wti", "query": "WTI crude", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "urals_discount", "query": "Urals discount", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "dubai_swap", "query": "Dubai swap", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "jkm", "query": "JKM LNG", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "ttf", "query": "TTF gas", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "lng_cargo", "query": "LNG cargo", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "strait_of_hormuz", "query": "Strait of Hormuz", "commodity": "crude", "theme": "chokepoints"},
    {"slug": "red_sea_shipping", "query": "Red Sea shipping", "commodity": "crude", "theme": "chokepoints"},
    {"slug": "bab_el_mandeb", "query": "Bab el-Mandeb", "commodity": "crude", "theme": "chokepoints"},
    {"slug": "nnpc", "query": "NNPC Nigeria oil", "commodity": "crude", "theme": "opec_producers"},
    {"slug": "kurdistan_oil_exports", "query": "Kurdistan oil exports", "commodity": "crude", "theme": "opec_producers"},
    {"slug": "libya_noc", "query": "Libya NOC oil", "commodity": "crude", "theme": "opec_producers"},
    {"slug": "pdvsa", "query": "PDVSA Venezuela oil", "commodity": "crude", "theme": "opec_producers"},
    {"slug": "crack_spread", "query": "crack spread", "commodity": "products", "theme": "refining"},
    {"slug": "refinery_outage", "query": "refinery outage", "commodity": "products", "theme": "refining"},
]


def slugify(text: str) -> str:
    """The fixed, permanent slug rule (Spec 29). Series IDs built from these are
    permanent, so this rule must never change: lower-case, every run of
    non-alphanumeric characters becomes a single underscore, strip the ends."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `pytest tests/test_social_queries.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pipelines/social/queries.py tests/test_social_queries.py pipelines/social/CLAUDE.md
git commit -m "feat(social): frozen ticker set and topic query universe"
```

---

### Task 2: Reddit RSS client

**Files:**
- Create: `pipelines/social/client.py`
- Test: `tests/test_social_client.py`

**Interfaces:**
- Consumes: `pipelines.social.queries.SUBREDDITS`.
- Produces: `Post` TypedDict with keys `post_id: str`, `url: str`, `title: str`, `ts: pd.Timestamp`, `platform: str`, `query: str`, `score: int | None`, `num_comments: int | None`; and `fetch_reddit(query: str, subreddits: list[str] | None = None, limit: int = 25) -> list[Post]`. Tasks 3, 5 and 6 all depend on these exact names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_social_client.py
from __future__ import annotations

import pytest
from pipelines.social.client import fetch_reddit


@pytest.mark.vcr
def test_fetch_reddit_returns_typed_posts_with_the_query_attached() -> None:
    posts = fetch_reddit("Henry Hub", subreddits=["energy"], limit=25)

    assert posts, "cassette should carry at least one entry"
    first = posts[0]
    assert set(first) == {
        "post_id", "url", "title", "ts", "platform", "query", "score", "num_comments"
    }
    assert first["platform"] == "reddit"
    assert first["query"] == "Henry Hub"
    assert first["url"].startswith("http")
    assert first["title"]


@pytest.mark.vcr
def test_reddit_rss_posts_carry_missing_metrics_never_zero() -> None:
    # The single most important constraint in Spec 29. RSS has no score and no
    # comment count; writing 0 would be indistinguishable from a real zero --
    # the same failure mode Spec 17 caught in Adanos's zeroed rows.
    posts = fetch_reddit("Henry Hub", subreddits=["energy"], limit=25)

    assert all(p["score"] is None for p in posts)
    assert all(p["num_comments"] is None for p in posts)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_social_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.social.client'`

- [ ] **Step 3: Write `pipelines/social/client.py`**

```python
"""Self-hosted social fetchers (Spec 29). Adapted from TauricResearch/TradingAgents
(Apache-2.0) -- see this package's CLAUDE.md for the upstream commit. Upstream's
public fetchers return prompt-ready prose and its typed layer is underscore-private,
so the request handling is adapted here and canonical typed rows are returned instead.

Reddit needs no API key. The default path is the public Atom/RSS search feed; the
richer /search.json endpoint is reliably WAF-blocked (HTTP 403) for public clients
(upstream issue #862) and probing it on every call doubles request volume and trips
429 on the RSS fallback, so it is deliberately not used.

**RSS carries no score and no comment count.** Those fields are None, never 0 --
a fabricated zero would be indistinguishable from a real zero (the Spec 17
zeroed-row lesson). Callers must not coerce them.

No client-side retry loop beyond a single Retry-After backoff on 429, matching
pipelines/adanos/client.py's plain style; per-platform resilience lives in
pull_social.py, matching pipelines/macro/pull_macro.py's established pattern."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import TypedDict
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from pipelines.social.queries import SUBREDDITS

REQUEST_TIMEOUT_SECONDS = 30
# Descriptive and identified, per Reddit's own API etiquette.
USER_AGENT = "energy-dashboard/0.1 (Kardamow research dashboard)"
_RSS_URL = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_MAX_RETRY_AFTER_SECONDS = 60


class Post(TypedDict):
    post_id: str
    url: str
    title: str
    ts: pd.Timestamp
    platform: str
    query: str
    # None means "this platform does not expose the metric", NOT zero. Never coerce.
    score: int | None
    num_comments: int | None


def _get(url: str) -> bytes:
    """Single request, with exactly one Retry-After backoff on 429 (Reddit's
    per-IP rate limit is real and easy to trip). Any other HTTPError propagates."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
            return body
    except HTTPError as exc:
        if exc.code != 429:
            raise
        wait = min(float(exc.headers.get("Retry-After") or 5), _MAX_RETRY_AFTER_SECONDS)
        time.sleep(wait)
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body_retry: bytes = response.read()
            return body_retry


def _parse_atom(raw: bytes, query: str) -> list[Post]:
    root = ET.fromstring(raw)
    posts: list[Post] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        link = entry.find("atom:link", _ATOM_NS)
        title = entry.find("atom:title", _ATOM_NS)
        updated = entry.find("atom:updated", _ATOM_NS)
        entry_id = entry.find("atom:id", _ATOM_NS)
        if link is None or title is None or updated is None:
            continue
        url = link.attrib.get("href", "")
        if not url:
            continue
        posts.append(
            Post(
                post_id=(entry_id.text if entry_id is not None and entry_id.text else url),
                url=url,
                title=(title.text or "").strip(),
                ts=pd.Timestamp(updated.text),
                platform="reddit",
                query=query,
                # RSS genuinely has neither. See this module's docstring.
                score=None,
                num_comments=None,
            )
        )
    return posts


def fetch_reddit(
    query: str, subreddits: list[str] | None = None, limit: int = 25
) -> list[Post]:
    """Search each subreddit's public RSS feed for `query`. Returns typed rows;
    duplicates across subreddits are left in place and deduped downstream by
    event_id (a hash of the URL), matching pipelines/news/events.py's approach."""
    posts: list[Post] = []
    for sub in subreddits if subreddits is not None else SUBREDDITS:
        qs = urlencode({"q": query, "restrict_sr": "on", "sort": "new", "limit": limit})
        posts.extend(_parse_atom(_get(_RSS_URL.format(sub=sub, qs=qs)), query))
    return posts
```

- [ ] **Step 4: Record the cassette and run the tests**

Run: `pytest tests/test_social_client.py -v --record-mode=once`
Then re-run in replay to prove the cassette works: `pytest tests/test_social_client.py -v`
Expected: 2 passed. Inspect `tests/cassettes/test_social_client/` and confirm no credentials landed in it.

- [ ] **Step 5: Commit**

```bash
git add pipelines/social/client.py tests/test_social_client.py tests/cassettes/test_social_client/
git commit -m "feat(social): Reddit RSS fetcher with missing-not-zero metrics"
```

---

### Task 3: Polymarket and StockTwits fetchers

Implement only the platforms Task 0 confirmed work unauthenticated. If one failed verification, drop it from `PLATFORMS` in `queries.py`, record why in `CLAUDE.md`, and skip its half of this task — do not invent a workaround.

**Files:**
- Modify: `pipelines/social/client.py`
- Modify: `tests/test_social_client.py`

**Interfaces:**
- Consumes: `Post`, `_get` from Task 2.
- Produces: `fetch_polymarket(query: str, limit: int = 25) -> list[Post]` and `fetch_stocktwits(symbol: str, limit: int = 25) -> list[Post]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_social_client.py`:

```python
from pipelines.social.client import fetch_polymarket, fetch_stocktwits


@pytest.mark.vcr
def test_fetch_polymarket_returns_typed_posts() -> None:
    posts = fetch_polymarket("oil", limit=5)

    assert posts
    assert all(p["platform"] == "polymarket" for p in posts)
    assert all(p["query"] == "oil" for p in posts)
    assert all(isinstance(p["title"], str) and p["title"] for p in posts)


@pytest.mark.vcr
def test_fetch_stocktwits_returns_typed_posts_with_real_metrics() -> None:
    posts = fetch_stocktwits("XOM", limit=5)

    assert posts
    assert all(p["platform"] == "stocktwits" for p in posts)
    # StockTwits' JSON API does expose no score either -- assert whatever Task 0
    # actually confirmed live, and leave the field None if the API has no such field.
    assert all(p["score"] is None or isinstance(p["score"], int) for p in posts)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_social_client.py -v -k "polymarket or stocktwits"`
Expected: FAIL with `ImportError: cannot import name 'fetch_polymarket'`

- [ ] **Step 3: Implement both fetchers**

Adjust the field names to the ones Task 0 actually recorded — these are written against the shapes documented at the time of writing and are exactly the kind of guess Task 0 exists to correct.

```python
import json

_POLYMARKET_URL = "https://gamma-api.polymarket.com/events?{qs}"
_STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"


def fetch_polymarket(query: str, limit: int = 25) -> list[Post]:
    """Prediction-market events matching `query`. Confirmed shape recorded in this
    package's CLAUDE.md. Polymarket has no post score, so `score` stays None."""
    qs = urlencode({"limit": limit, "active": "true", "search": query})
    payload = json.loads(_get(_POLYMARKET_URL.format(qs=qs)))
    rows = payload if isinstance(payload, list) else payload.get("data", [])

    posts: list[Post] = []
    for row in rows:
        slug = row.get("slug") or row.get("id")
        title = (row.get("title") or "").strip()
        if not slug or not title:
            continue
        posts.append(
            Post(
                post_id=str(slug),
                url=f"https://polymarket.com/event/{slug}",
                title=title,
                ts=pd.Timestamp(row.get("startDate") or row.get("createdAt")),
                platform="polymarket",
                query=query,
                score=None,
                num_comments=None,
            )
        )
    return posts


def fetch_stocktwits(symbol: str, limit: int = 25) -> list[Post]:
    """Public symbol stream. `symbol` is a ticker, so this feeds Set A only."""
    payload = json.loads(_get(_STOCKTWITS_URL.format(symbol=symbol)))
    messages = payload.get("messages", [])[:limit]

    posts: list[Post] = []
    for message in messages:
        body = (message.get("body") or "").strip()
        message_id = message.get("id")
        if not body or message_id is None:
            continue
        posts.append(
            Post(
                post_id=str(message_id),
                url=f"https://stocktwits.com/message/{message_id}",
                title=body,
                ts=pd.Timestamp(message["created_at"]),
                platform="stocktwits",
                query=symbol,
                score=None,
                num_comments=None,
            )
        )
    return posts
```

- [ ] **Step 4: Record cassettes and verify**

Run: `pytest tests/test_social_client.py -v --record-mode=once` then `pytest tests/test_social_client.py -v`
Expected: 4 passed (or 3 with a documented StockTwits drop).

- [ ] **Step 5: Commit**

```bash
git add pipelines/social/client.py tests/test_social_client.py tests/cassettes/test_social_client/
git commit -m "feat(social): Polymarket and StockTwits fetchers"
```

---

### Task 4: Deterministic lexicon scoring

**Files:**
- Modify: `pyproject.toml`
- Create: `pipelines/social/score.py`
- Test: `tests/test_social_score.py`

**Interfaces:**
- Consumes: `Post` from Task 2; `slugify`, `TopicQuery` from Task 1.
- Produces: `score_text(text: str) -> float` (−1..+1) and `aggregate_to_ts_long(posts: list[Post], subject: str, ingested_at: pd.Timestamp) -> pd.DataFrame` returning canonical `ts_long` columns.

- [ ] **Step 1: Add the dependency — this is the rule 7 ask, confirm before running**

Add to `pyproject.toml`'s `dependencies`, in the justified style the file already uses:

```toml
    # Spec 29's deterministic sentiment scorer. Chosen over an LLM deliberately: the
    # test story is vcrpy cassettes and 00_TRADING_CONVENTIONS requires a model card
    # for anything estimated, so a reproducible offline scorer is the right trade for
    # a series whose entire purpose is to be compared against a vendor's. VADER is
    # calibrated on general social-media English, not energy jargon -- "crude tanking"
    # is bearish price language, not negative sentiment. Confirmed with the user
    # before adding (root CLAUDE.md rule 7).
    "vaderSentiment>=3.3,<4",
```

Then: `uv sync`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_social_score.py
from __future__ import annotations

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.social.client import Post
from pipelines.social.score import aggregate_to_ts_long, score_text


def _post(title: str, ts: str) -> Post:
    return Post(
        post_id=title, url=f"https://example.test/{title}", title=title,
        ts=pd.Timestamp(ts), platform="reddit", query="Henry Hub",
        score=None, num_comments=None,
    )


def test_score_text_is_deterministic_and_bounded() -> None:
    assert score_text("This is great news") == score_text("This is great news")
    assert -1.0 <= score_text("This is great news") <= 1.0
    assert score_text("This is great news") > 0
    assert score_text("terrible awful disaster") < 0
    assert score_text("") == 0.0


def test_aggregate_produces_valid_ts_long_with_post_count_and_sentiment() -> None:
    posts = [_post("great news", "2026-09-01T10:00Z"), _post("awful", "2026-09-01T12:00Z")]

    rows = aggregate_to_ts_long(posts, subject="henry_hub", ingested_at=pd.Timestamp("2026-09-01T18:00Z"))

    validate_ts_long(rows)
    ids = set(rows["series_id"])
    assert "social.reddit.henry_hub.post_count" in ids
    assert "social.reddit.henry_hub.sentiment_score" in ids
    count_row = rows[rows["series_id"] == "social.reddit.henry_hub.post_count"].iloc[0]
    assert count_row["value"] == 2.0
    assert count_row["unit"] == "count"
    assert count_row["source"] == "reddit"
    assert count_row["freq"] == "D"


def test_aggregate_returns_empty_for_no_posts_never_a_zero_row() -> None:
    # A zero post_count row would assert "we looked and found nothing" on a day we
    # may simply not have looked. Absent means absent -- the Spec 17 lesson.
    rows = aggregate_to_ts_long([], subject="henry_hub", ingested_at=pd.Timestamp("2026-09-01T18:00Z"))
    assert rows.empty
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_social_score.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.social.score'`

- [ ] **Step 4: Write `pipelines/social/score.py`**

```python
"""Deterministic lexicon scoring for Spec 29.

Deliberately not an LLM. The project's test story is vcrpy cassettes and
00_TRADING_CONVENTIONS requires a model card with window/refit/OOS for anything
estimated; a lexicon scorer is reproducible, offline and free, so the same text
always yields the same score and a regression is a real regression. LLM scoring is
deferred to its own spec, where it would land as a separately-named social_llm.*
series with a pinned model ID -- never as a silent upgrade to social.*.

Honest limitation, stated rather than hidden: VADER is calibrated on general
social-media English, not energy-trading jargon. "Crude tanking" is bearish price
language, not negative sentiment about crude."""

from __future__ import annotations

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from pipelines.social.client import Post

COUNT_UNIT = "count"
SENTIMENT_UNIT = "score_neg1_to_1"

_ANALYSER = SentimentIntensityAnalyzer()


def score_text(text: str) -> float:
    """VADER's compound score, already on -1..+1. Empty text scores exactly 0.0."""
    if not text.strip():
        return 0.0
    compound: float = _ANALYSER.polarity_scores(text)["compound"]
    return compound


def aggregate_to_ts_long(
    posts: list[Post], subject: str, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """One post_count row and one sentiment_score row per (platform, day) for
    `subject`. Returns an empty frame when there are no posts -- a zero post_count
    row would assert "we looked and found nothing" on a day we may not have looked
    at all, which is exactly the fabricated-zero failure Spec 17 caught."""
    if not posts:
        return pd.DataFrame()

    frame = pd.DataFrame(
        {
            "platform": [p["platform"] for p in posts],
            "day": [pd.Timestamp(p["ts"]).tz_localize(None).normalize() for p in posts],
            "sentiment": [score_text(p["title"]) for p in posts],
        }
    )

    rows: list[dict[str, object]] = []
    for (platform, day), group in frame.groupby(["platform", "day"]):
        base = {
            "source": platform,
            "ts": day,
            "geo": "",
            "freq": "D",
            "revision_date": ingested_at,
        }
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.post_count",
                "value": float(len(group)),
                "unit": COUNT_UNIT,
            }
        )
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.sentiment_score",
                "value": float(group["sentiment"].mean()),
                "unit": SENTIMENT_UNIT,
            }
        )
    return pd.DataFrame(rows)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_social_score.py -v`
Expected: 3 passed. If `validate_ts_long` rejects a dtype, fix the frame construction — do not relax the validator.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml pipelines/social/score.py tests/test_social_score.py uv.lock
git commit -m "feat(social): deterministic VADER scoring and ts_long aggregation"
```

---

### Task 5: Posts to events

**Files:**
- Create: `pipelines/social/events.py`
- Test: `tests/test_social_events.py`

**Interfaces:**
- Consumes: `Post` (Task 2); `extract_geo`, `extract_severity`, `extract_tags` from `pipelines.news.tagging`.
- Produces: `posts_to_events(posts: list[Post], commodity: str) -> pd.DataFrame` returning canonical `events` columns.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_social_events.py
from __future__ import annotations

import hashlib

import pandas as pd
from core.schemas import validate_events
from pipelines.social.client import Post
from pipelines.social.events import posts_to_events


def _post(title: str, url: str) -> Post:
    return Post(
        post_id=url, url=url, title=title, ts=pd.Timestamp("2026-09-01T10:00Z"),
        platform="reddit", query="Henry Hub", score=None, num_comments=None,
    )


def test_posts_to_events_uses_the_same_event_id_hash_as_the_news_pipeline() -> None:
    url = "https://reddit.com/r/energy/comments/abc"
    events = posts_to_events([_post("Henry Hub spikes", url)], commodity="gas")

    validate_events(events)
    assert events.iloc[0]["event_id"] == hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert events.iloc[0]["source"] == "reddit"
    assert events.iloc[0]["commodity"] == "gas"
    assert "Henry Hub" in events.iloc[0]["tags"]


def test_empty_posts_return_a_correctly_typed_empty_frame() -> None:
    events = posts_to_events([], commodity="gas")
    assert events.empty
    validate_events(events)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_social_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.social.events'`

- [ ] **Step 3: Write `pipelines/social/events.py`**

```python
"""Social posts -> the existing `events` schema (Spec 29 adds no new schema).

event_id is the same sha256-of-URL used by pipelines/news/events.py, so
write_events' dedup works unchanged and re-pulling the same post on a later run
maps to the same row. Tagging reuses pipelines/news/tagging.py rather than
introducing a second tagger with its own drift."""

from __future__ import annotations

import hashlib

import pandas as pd

from core.schemas import EVENTS_SCHEMA
from pipelines.news.tagging import extract_geo, extract_severity, extract_tags
from pipelines.social.client import Post

# Posts are chatter, not events with intensity. Severity is derived from the text
# where the news tagger recognises something, and floors at 1 otherwise.
_MIN_SEVERITY = 1


def _event_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def posts_to_events(posts: list[Post], commodity: str) -> pd.DataFrame:
    """`commodity` comes from the TopicQuery that produced these posts (Set B) or
    is "equity" for ticker queries (Set A)."""
    if not posts:
        # Building from the real pyarrow schema's own empty table gives correct
        # dtypes for free -- a bare DataFrame(columns=[...]) leaves every dtype
        # "object" and fails validate_events. Same trick pipelines/news/events.py
        # and core/storage.py's _read both use.
        empty: pd.DataFrame = EVENTS_SCHEMA.empty_table().to_pandas()
        return empty

    titles = [p["title"] for p in posts]
    return pd.DataFrame(
        {
            "event_id": [_event_id(p["url"]) for p in posts],
            "ts": [pd.Timestamp(p["ts"]).tz_localize(None) for p in posts],
            "headline": titles,
            "source": [p["platform"] for p in posts],
            "url": [p["url"] for p in posts],
            # The matching query travels with the row so a post's provenance is
            # readable straight from the lake.
            "tags": [sorted({p["query"], *extract_tags(p["title"])}) for p in posts],
            "geo": [extract_geo(title) for title in titles],
            "commodity": commodity,
            "severity": [max(extract_severity(title), _MIN_SEVERITY) for title in titles],
            "language": "en",
        }
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_social_events.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add pipelines/social/events.py tests/test_social_events.py
git commit -m "feat(social): map posts onto the existing events schema"
```

---

### Task 6: Pull orchestration, resilience and scheduling

**Files:**
- Create: `pipelines/social/pull_social.py`
- Create: `pipelines/social/pull_weekly.py`
- Modify: `infra/run_scheduled.py` (the `weekly_fri` list)
- Test: `tests/test_social_pull.py`

**Interfaces:**
- Consumes: `fetch_reddit`, `fetch_polymarket`, `fetch_stocktwits` (Tasks 2–3); `aggregate_to_ts_long` (Task 4); `posts_to_events` (Task 5); `TICKER_QUERIES`, `TOPIC_QUERIES`, `PLATFORMS` (Task 1); `write_ts_long`, `write_events` from `core.storage`.
- Produces: `pull_topic(topic, ingested_at) -> tuple[pd.DataFrame, pd.DataFrame]`, `pull_ticker(ticker, ingested_at) -> tuple[pd.DataFrame, pd.DataFrame]`, `main() -> None`.

- [ ] **Step 1: Write the failing resilience test**

```python
# tests/test_social_pull.py
from __future__ import annotations

import pandas as pd
import pytest
import requests
from pipelines.social import pull_social
from pipelines.social.client import Post


def _post(title: str, url: str, platform: str, query: str) -> Post:
    return Post(
        post_id=url, url=url, title=title, ts=pd.Timestamp("2026-09-01T10:00Z"),
        platform=platform, query=query, score=None, num_comments=None,
    )


def test_one_platform_failing_never_aborts_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pattern pipelines/macro/pull_macro.py established and Spec 17 reused:
    # per-platform resilience, not just per-request retry.
    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("polymarket down")

    monkeypatch.setattr(
        pull_social, "fetch_reddit",
        lambda query, **kw: [_post("great news", "https://x.test/1", "reddit", query)],
    )
    monkeypatch.setattr(pull_social, "fetch_polymarket", boom)

    topic = {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"}
    rows, events = pull_social.pull_topic(topic, pd.Timestamp("2026-09-01T18:00Z"))

    assert not rows.empty, "reddit's rows must survive polymarket failing"
    assert set(rows["source"]) == {"reddit"}
    assert len(events) == 1


def test_a_topic_with_no_posts_writes_nothing_rather_than_zeros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pull_social, "fetch_reddit", lambda query, **kw: [])
    monkeypatch.setattr(pull_social, "fetch_polymarket", lambda query, **kw: [])

    topic = {"slug": "pdvsa", "query": "PDVSA", "commodity": "crude", "theme": "opec_producers"}
    rows, events = pull_social.pull_topic(topic, pd.Timestamp("2026-09-01T18:00Z"))

    assert rows.empty
    assert events.empty
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_social_pull.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipelines.social.pull_social'`

- [ ] **Step 3: Write `pipelines/social/pull_social.py`**

```python
"""Weekly entrypoint for Spec 29. Fetches Set A (ticker queries, for the Adanos
overlap) and Set B (commodity/geopolitical topics, which Adanos cannot express),
scores both deterministically, and writes ts_long aggregates plus the raw posts
as events.

Per-platform resilience, not just per-request retry -- matches
pipelines/macro/pull_macro.py's established pattern and pipelines/adanos/
pull_adanos.py's reuse of it: one flaky platform must never abort the rest.

Registered in the weekly_fri group beside adanos deliberately, so the overlap join
in core/sentiment.py has matching dates rather than a systematic one-day offset
that would masquerade as deviation."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests

from core.storage import write_events, write_ts_long
from pipelines.social.client import fetch_polymarket, fetch_reddit, fetch_stocktwits
from pipelines.social.events import posts_to_events
from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES, TopicQuery
from pipelines.social.score import aggregate_to_ts_long

TICKER_COMMODITY = "equity"


def _safe_fetch(label: str, fetch: object, *args: object) -> list[object]:
    """Any one platform's network failure is logged and skipped, never raised."""
    try:
        return list(fetch(*args))  # type: ignore[operator]
    except requests.exceptions.RequestException as exc:
        print(f"social {label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
        return []
    except OSError as exc:
        # urllib raises URLError/HTTPError (OSError subclasses), not requests'.
        print(f"social {label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
        return []


def pull_topic(
    topic: TopicQuery, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Set B. Returns (ts_long rows, events rows), both possibly empty -- an empty
    result for a topic is a real finding (recorded in this package's CLAUDE.md),
    not a bug to paper over with zeros."""
    query = topic["query"]
    posts = [
        *_safe_fetch(f"reddit {query}", fetch_reddit, query),
        *_safe_fetch(f"polymarket {query}", fetch_polymarket, query),
    ]
    print(f"social topic {topic['slug']}: {len(posts)} posts", flush=True)

    rows = aggregate_to_ts_long(posts, subject=topic["slug"], ingested_at=ingested_at)
    events = posts_to_events(posts, commodity=topic["commodity"])
    return rows, events


def pull_ticker(
    ticker: str, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Set A -- exists solely to give core/sentiment.py an apples-to-apples series
    against Adanos for the same ticker, platform and day."""
    posts = [
        *_safe_fetch(f"reddit {ticker}", fetch_reddit, ticker),
        *_safe_fetch(f"stocktwits {ticker}", fetch_stocktwits, ticker),
    ]
    print(f"social ticker {ticker}: {len(posts)} posts", flush=True)

    rows = aggregate_to_ts_long(posts, subject=ticker.lower(), ingested_at=ingested_at)
    events = posts_to_events(posts, commodity=TICKER_COMMODITY)
    return rows, events


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))

    row_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    for topic in TOPIC_QUERIES:
        rows, events = pull_topic(topic, ingested_at)
        row_frames.append(rows)
        event_frames.append(events)
    for ticker in TICKER_QUERIES:
        rows, events = pull_ticker(ticker, ingested_at)
        row_frames.append(rows)
        event_frames.append(events)

    rows_all = [f for f in row_frames if not f.empty]
    if rows_all:
        combined = pd.concat(rows_all, ignore_index=True)
        for source, group in combined.groupby("source"):
            write_ts_long(group.reset_index(drop=True), source=str(source))
        print(f"wrote {len(combined)} social rows", flush=True)
    else:
        print("no social rows pulled", flush=True)

    events_all = [f for f in event_frames if not f.empty]
    if events_all:
        combined_events = pd.concat(events_all, ignore_index=True)
        # Drop within-run duplicates first: the same post can match several queries
        # and several subreddits, and they share an event_id by construction.
        combined_events = combined_events.drop_duplicates(subset="event_id", keep="first")
        for source, group in combined_events.groupby("source"):
            write_events(group.reset_index(drop=True), source=str(source))
        print(f"wrote {len(combined_events)} social events", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `pipelines/social/pull_weekly.py`**

```python
"""Thin re-export so infra/run_scheduled.py's cadence groups can address this
pipeline by the same pull_<cadence> convention every other pipeline uses (the
precedent is pipelines/macro/pull_weekly.py and pipelines/adanos/pull_weekly.py)."""

from __future__ import annotations

from pipelines.social.pull_social import main

__all__ = ["main"]
```

- [ ] **Step 5: Register in the scheduler**

In `infra/run_scheduled.py`, add to the `"weekly_fri"` list, directly after the `adanos` entry:

```python
        ("social", "pipelines.social.pull_weekly"),
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_social_pull.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add pipelines/social/pull_social.py pipelines/social/pull_weekly.py infra/run_scheduled.py tests/test_social_pull.py
git commit -m "feat(social): pull orchestration with per-platform resilience"
```

---

### Task 7: Reconciliation in `core/sentiment.py`

**Files:**
- Create: `core/sentiment.py`
- Test: `tests/test_sentiment.py`

**Interfaces:**
- Consumes: `read_ts_long` from `core.storage`.
- Produces: frozen dataclass `Overlap` with fields `frame: pd.DataFrame` (columns `ts`, `adanos`, `social`, `gap`), `overlap_days: int`, `dropped_days: int`; plus `overlap(ticker: str, platform: str = "reddit") -> Overlap`, `agreement_rate(frame: pd.DataFrame) -> float`, `rolling_correlation(frame: pd.DataFrame, window: int = 14) -> pd.Series`. Task 8 consumes all four.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sentiment.py
from __future__ import annotations

import pandas as pd
import pytest
from core.sentiment import agreement_rate, overlap, rolling_correlation


def _lake_rows() -> pd.DataFrame:
    # Adanos has 01-03; social has 02-04. Only 02 and 03 overlap.
    return pd.DataFrame(
        {
            "series_id": (
                ["adanos.reddit.xom.sentiment_score"] * 3
                + ["social.reddit.xom.sentiment_score"] * 3
            ),
            "ts": pd.to_datetime(
                ["2026-09-01", "2026-09-02", "2026-09-03",
                 "2026-09-02", "2026-09-03", "2026-09-04"]
            ),
            "value": [0.5, 0.4, -0.2, 0.1, 0.3, 0.9],
        }
    )


def test_overlap_is_an_inner_join_that_counts_what_it_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A deviation computed over 3 overlapping days is not a finding, so the count
    # must travel with the frame rather than being silently discarded.
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: _lake_rows())

    result = overlap("XOM", platform="reddit")

    assert result.overlap_days == 2
    assert result.dropped_days == 2
    assert list(result.frame["ts"].dt.strftime("%Y-%m-%d")) == ["2026-09-02", "2026-09-03"]


def test_gap_is_signed_social_minus_adanos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: _lake_rows())

    frame = overlap("XOM", platform="reddit").frame

    assert frame.iloc[0]["gap"] == pytest.approx(0.1 - 0.4)
    assert frame.iloc[1]["gap"] == pytest.approx(0.3 - (-0.2))


def test_agreement_rate_is_the_share_of_days_the_two_agree_on_sign() -> None:
    frame = pd.DataFrame({"adanos": [0.4, -0.2, 0.5], "social": [0.1, 0.3, 0.2]})
    # Day 1 both positive (agree), day 2 signs differ, day 3 both positive (agree).
    assert agreement_rate(frame) == pytest.approx(2 / 3)


def test_no_overlap_returns_an_empty_frame_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: pd.DataFrame())

    result = overlap("XOM", platform="reddit")

    assert result.frame.empty
    assert result.overlap_days == 0
    assert agreement_rate(result.frame) == 0.0


def test_rolling_correlation_returns_a_series_of_the_right_length() -> None:
    frame = pd.DataFrame({"adanos": [0.1, 0.2, 0.3, 0.4], "social": [0.2, 0.1, 0.5, 0.3]})
    assert len(rolling_correlation(frame, window=2)) == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_sentiment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.sentiment'`

- [ ] **Step 3: Write `core/sentiment.py`**

```python
"""Spec 29's two-source reconciliation -- the only place the adanos.* and social.*
namespaces meet.

The two are never blended. No weighted average, no "consensus" series: the two
numbers and the signed gap between them are the output. This is the same
convention the trading layer already applies to published benchmarks shown beside
repo estimates with the deviation, rather than merged into one.

Only the two sentiment_score series are comparable -- both are on -1..+1. Adanos's
buzz_score (0-100) and our post_count are different quantities and are deliberately
not compared."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.storage import read_ts_long

DEFAULT_CORRELATION_WINDOW = 14


@dataclass(frozen=True)
class Overlap:
    """`dropped_days` travels with the frame on purpose: a deviation computed over
    three overlapping days is not a finding, and the UI must be able to say so."""

    frame: pd.DataFrame
    overlap_days: int
    dropped_days: int


def overlap(ticker: str, platform: str = "reddit") -> Overlap:
    """Inner-join the vendor and self-hosted sentiment series for one ticker and
    platform. Columns: ts, adanos, social, gap (signed, social - adanos)."""
    subject = ticker.lower()
    adanos_id = f"adanos.{platform}.{subject}.sentiment_score"
    social_id = f"social.{platform}.{subject}.sentiment_score"

    raw = read_ts_long(series_ids=[adanos_id, social_id])
    if raw.empty:
        return Overlap(frame=pd.DataFrame(columns=["ts", "adanos", "social", "gap"]),
                       overlap_days=0, dropped_days=0)

    wide = (
        raw.assign(day=pd.to_datetime(raw["ts"]).dt.normalize())
        .pivot_table(index="day", columns="series_id", values="value", aggfunc="mean")
        .rename(columns={adanos_id: "adanos", social_id: "social"})
    )
    for column in ("adanos", "social"):
        if column not in wide.columns:
            wide[column] = pd.NA

    total_days = len(wide)
    joined = wide.dropna(subset=["adanos", "social"]).reset_index(names="ts")
    joined["gap"] = joined["social"].astype(float) - joined["adanos"].astype(float)

    return Overlap(
        frame=joined[["ts", "adanos", "social", "gap"]],
        overlap_days=len(joined),
        dropped_days=total_days - len(joined),
    )


def agreement_rate(frame: pd.DataFrame) -> float:
    """Share of overlapping days where the two sources agree on the sign of
    sentiment. 0.0 for an empty frame -- no days, no agreement to report."""
    if frame.empty:
        return 0.0
    import numpy as np

    agree = np.sign(frame["adanos"].astype(float)) == np.sign(frame["social"].astype(float))
    return float(agree.mean())


def rolling_correlation(
    frame: pd.DataFrame, window: int = DEFAULT_CORRELATION_WINDOW
) -> pd.Series:
    """Rolling correlation between the two sources over `window` overlapping days.
    Short frames yield NaNs rather than a fabricated single-point correlation."""
    if frame.empty:
        return pd.Series(dtype="float64")
    return (
        frame["adanos"].astype(float).rolling(window).corr(frame["social"].astype(float))
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_sentiment.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/sentiment.py tests/test_sentiment.py
git commit -m "feat(sentiment): two-source reconciliation, never blended"
```

---

### Task 8: Page section on `10_macro.py`

**Files:**
- Modify: `apps/dashboard/pages/10_macro.py` (add three section functions plus one call site; do not touch the existing `_adanos_*` functions)

**Interfaces:**
- Consumes: `overlap`, `agreement_rate` (Task 7); `TICKER_QUERIES`, `TOPIC_QUERIES` (Task 1); existing `card`, `kardamow_take`, `read_ts_long`, `NAVY`, `LIGHT_BLUE`, `RED`, `simple_time_series_chart`.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the imports**

Add to the existing import block:

```python
from core.sentiment import agreement_rate, overlap
from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES
```

- [ ] **Step 2: Add the three section functions**

Place them immediately after `_adanos_sentiment_section`:

```python
def _social_comparison_section() -> None:
    ticker = st.selectbox("Ticker", options=TICKER_QUERIES, key="social_ticker")
    result = overlap(ticker, platform="reddit")
    if result.frame.empty:
        st.info("No overlapping Adanos/self-hosted days yet — run `pipelines/social/pull_social.py`.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=result.frame["ts"], y=result.frame["adanos"], name="Adanos (vendor)",
                   mode="lines", line={"color": NAVY, "width": 2})
    )
    fig.add_trace(
        go.Scatter(x=result.frame["ts"], y=result.frame["social"], name="Self-hosted",
                   mode="lines", line={"color": LIGHT_BLUE, "width": 2})
    )
    fig.add_annotation(
        x=result.frame["ts"].iloc[-1], y=result.frame["social"].iloc[-1],
        text=(f"{result.overlap_days} overlapping days · "
              f"{result.dropped_days} dropped · "
              f"{agreement_rate(result.frame):.0%} sign agreement"),
        showarrow=True, xanchor="right",
    )
    fig.update_layout(title=f"{ticker} sentiment — vendor vs self-hosted",
                      yaxis_title="Sentiment (-1 to +1)")
    with card(f"{ticker}: Adanos vs self-hosted"):
        st.plotly_chart(fig, use_container_width=True)
        if result.overlap_days < 10:
            st.caption(
                f"Only {result.overlap_days} overlapping days — too few to read as a "
                "finding. Both series need history before the gap means anything."
            )


def _social_deviation_section() -> None:
    ticker = st.session_state.get("social_ticker", TICKER_QUERIES[0])
    result = overlap(ticker, platform="reddit")
    if result.frame.empty:
        return

    disagree = result.frame["adanos"] * result.frame["social"] < 0
    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=result.frame["ts"], y=result.frame["gap"], name="Self-hosted − Adanos",
               marker={"color": [RED if d else NAVY for d in disagree]})
    )
    fig.update_layout(title=f"{ticker} deviation (self-hosted − Adanos)",
                      yaxis_title="Difference")
    with card("Deviation"):
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Red bars mark days where the two sources disagree on sign.")


def _social_topic_attention_section() -> None:
    ids = [f"social.reddit.{q['slug']}.post_count" for q in TOPIC_QUERIES]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        st.info("No social topic data yet — run `pipelines/social/pull_social.py`.")
        return

    df = df.copy()
    df["topic"] = df["series_id"].str.split(".").str[2]
    latest = df.sort_values("ts").groupby("topic", as_index=False).last()
    latest = latest.sort_values("value", ascending=False)

    fig = go.Figure(
        go.Bar(x=latest["topic"], y=latest["value"], marker={"color": NAVY})
    )
    fig.update_layout(title="Latest post counts by topic", yaxis_title="Posts")
    with card("Topic attention"):
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "These topics have no Adanos counterpart — a ticker basket cannot "
            "express them. Attention only, not sentiment."
        )


def _social_sentiment_section() -> None:
    _social_comparison_section()
    _social_deviation_section()
    _social_topic_attention_section()
    kardamow_take(
        "Two independent readings of the same chatter, shown side by side rather "
        "than averaged into one. Where they disagree, neither is authoritative — "
        "the gap is the information. Attention and flow data, never a trading signal."
    )
```

- [ ] **Step 3: Add the call site**

Find the existing line that calls `_adanos_sentiment_section()` near the bottom of the page and add below it:

```python
st.subheader("Self-hosted social sentiment")
_social_sentiment_section()
```

- [ ] **Step 4: Verify in the real app**

Run: `streamlit run apps/dashboard/app.py`
Open the Macro & FX page. Confirm: the new subheader renders below the Adanos section; with an empty lake the three `st.info` empty states appear rather than a traceback; after running `python -m pipelines.social.pull_social` the charts render in house style (navy/light-blue, `card`-wrapped).

- [ ] **Step 5: Commit**

```bash
git add apps/dashboard/pages/10_macro.py
git commit -m "feat(page10): self-hosted social sentiment beside Adanos"
```

---

### Task 9: Full green and the untouched-files proof

**Files:** none created; this task verifies.

- [ ] **Step 1: Prove the protected files are unchanged**

```bash
git diff --stat main -- pipelines/adanos/ specs/17_adanos-sentiment-overlay.md core/schemas.py
```

Expected: **empty output**. Any diff here is an acceptance-criterion failure — revert it.

- [ ] **Step 2: Run the whole suite**

Run: `pytest`
Expected: all pass, including every pre-existing test.

- [ ] **Step 3: Lint and typecheck**

Run: `ruff check .` then `mypy core pipelines infra`
Expected: both clean.

- [ ] **Step 4: Update the spec index status**

In `specs/00_INDEX.md`, change Spec 29's Status cell from `not started` to a real one-line summary of what shipped, including any platform dropped at Task 0 and the real empty-query findings — the same honest style the Spec 18–21 rows use.

- [ ] **Step 5: Commit**

```bash
git add specs/00_INDEX.md
git commit -m "docs(spec29): record real implementation outcomes"
```

---

## Self-Review

**Spec coverage:** Every spec section maps to a task — objective/honesty rule → Task 8's `kardamow_take`; provenance/licence → Task 0 Step 5; real API shape verification → Task 0; query universe (Sets A and B, frozen tickers, slug rule) → Task 1; data model (events + ts_long, no new schema) → Tasks 4 and 5; deterministic scoring and the rule 7 dependency ask → Task 4; reconciliation → Task 7; pipeline structure and scheduling → Task 6; visualisation → Task 8; acceptance criteria → Task 9.

**Known gaps, deliberate:** The spec's acceptance criterion "a test proving RSS posts with no score/comment count are written as missing, not 0" is covered at the client boundary (Task 2 Step 1) rather than at the lake boundary, because `score`/`num_comments` are never written to `ts_long` at all — `post_count` is a count of rows, not a sum of scores. The stronger lake-level guarantee is Task 4's `test_aggregate_returns_empty_for_no_posts_never_a_zero_row`.

**Type consistency:** `Post` (Task 2) is consumed unchanged by Tasks 3–6. `aggregate_to_ts_long(posts, subject, ingested_at)` and `posts_to_events(posts, commodity)` keep the same signatures at every call site. `Overlap.frame` columns (`ts`, `adanos`, `social`, `gap`) are the ones Task 8 reads.

**Risk to watch:** Task 3's Polymarket and StockTwits field names are written from documented shapes, not verified ones. Task 0 exists to correct them, and its findings take precedence over the code in this plan.
