"""Self-hosted social fetchers (Spec 29). Adapted from TauricResearch/TradingAgents
(Apache-2.0) -- see this package's CLAUDE.md for the upstream commit. Upstream's
public fetchers return prompt-ready prose and its typed layer is underscore-private,
so the request handling is adapted here and canonical typed rows are returned instead.

Reddit needs no API key. Site-wide search (`www.reddit.com/search.rss`) was probed
live and confirmed NOT to filter by query at all -- see this package's CLAUDE.md for
the two probes that established this -- so this client searches per subreddit
instead, via `SUBREDDITS` (`pipelines/social/queries.py`), narrowed to two
subreddits to stay inside Reddit's confirmed ~1-request-per-60-seconds
unauthenticated rate limit. The richer /search.json endpoint is reliably
WAF-blocked (HTTP 403) for public clients (upstream issue #862) and probing it on
every call doubles request volume and trips 429 on the RSS fallback, so it is
deliberately not used.

**RSS carries no score and no comment count.** Those fields are None, never 0 --
a fabricated zero would be indistinguishable from a real zero (the Spec 17
zeroed-row lesson). Callers must not coerce them.

**Pacing is mandatory, not optional.** Reddit's own rate-limit headers confirmed
live: a first request returns `X-Ratelimit-Remaining: 0.0` with `X-Ratelimit-Reset`
already counting down, and a second request before that reset elapses returns
HTTP 429. Every request after the first therefore sleeps for the prior response's
`X-Ratelimit-Reset` (default `_DEFAULT_PACE_SECONDS` if the header is absent)
before firing. `_sleep` is a module-level hook (not a hardcoded `time.sleep` call)
so tests can patch it to a no-op rather than actually waiting out real rate limits.

No client-side retry loop beyond a single backoff-and-retry on 429, matching
pipelines/adanos/client.py's plain style; per-platform resilience lives in
pull_social.py, matching pipelines/macro/pull_macro.py's established pattern. The
429 backoff waits on `X-Ratelimit-Reset` rather than `Retry-After`: confirmed live,
Reddit's 429 response carries the former but not the latter."""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from email.message import Message
from typing import TypedDict
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from pipelines.social.queries import SUBREDDITS

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
# Descriptive and identified, per Reddit's own API etiquette.
USER_AGENT = "energy-dashboard/0.1 (Kardamow research dashboard)"
_RSS_URL = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# Reddit's own confirmed-live pace: ~1 unauthenticated request per 60 seconds.
# Used whenever a response carries no X-Ratelimit-Reset header to read instead.
_DEFAULT_PACE_SECONDS = 60.0
_POLYMARKET_URL = "https://gamma-api.polymarket.com/events?{qs}"
_STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
# Task 0 saw one unexplained HTTP 403 sandwiched between clean 200s, with no
# rate-limit header to size a backoff from -- a short fixed pause, not a
# computed one, is all the evidence supports.
_STOCKTWITS_RETRY_PAUSE_SECONDS = 2.0

# Swappable by tests (`monkeypatch.setattr(client, "_sleep", ...)`) so cassette
# replay never actually blocks for real minutes-long rate-limit waits.
_sleep = time.sleep


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


def _pace_seconds(headers: Message) -> float:
    """Seconds to wait before the next request, read off `X-Ratelimit-Reset`
    (confirmed live to be present on both 200 and 429 responses); falls back to
    `_DEFAULT_PACE_SECONDS` when the header is absent or unparseable."""
    try:
        return float(headers.get("X-Ratelimit-Reset", _DEFAULT_PACE_SECONDS))
    except (TypeError, ValueError):
        return _DEFAULT_PACE_SECONDS


def _get(url: str) -> tuple[bytes, float]:
    """Single request, with exactly one backoff-and-retry on 429 (Reddit's
    per-IP rate limit is real and easy to trip). Any other HTTPError propagates.
    Returns the body plus the pace to honour before the *next* request."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read(), _pace_seconds(response.headers)
    except HTTPError as exc:
        if exc.code != 429:
            raise
        _sleep(_pace_seconds(exc.headers))
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as retried:
            return retried.read(), _pace_seconds(retried.headers)


def _parse_atom(raw: bytes, query: str) -> list[Post]:
    root = ET.fromstring(raw)
    posts: list[Post] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        link = entry.find("atom:link", _ATOM_NS)
        title = entry.find("atom:title", _ATOM_NS)
        published = entry.find("atom:published", _ATOM_NS)
        updated = entry.find("atom:updated", _ATOM_NS)
        # Prefer published, fall back to updated (confirmed live the two
        # duplicate on every entry, but published is the more precise name).
        timestamp = published if published is not None and published.text else updated
        entry_id = entry.find("atom:id", _ATOM_NS)
        if link is None or title is None or timestamp is None or not timestamp.text:
            continue
        url = link.attrib.get("href", "")
        if not url:
            continue
        posts.append(
            Post(
                post_id=(entry_id.text if entry_id is not None and entry_id.text else url),
                url=url,
                title=(title.text or "").strip(),
                ts=pd.Timestamp(timestamp.text),
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
    event_id (a hash of the URL), matching pipelines/news/events.py's approach.
    Consecutive requests are paced on the prior response's `X-Ratelimit-Reset`
    (Reddit's unauthenticated quota is confirmed live at ~1 request/60s)."""
    posts: list[Post] = []
    pace_seconds: float | None = None
    for sub in subreddits if subreddits is not None else SUBREDDITS:
        if pace_seconds is not None:
            _sleep(pace_seconds)
        qs = urlencode({"q": query, "restrict_sr": "on", "sort": "new", "limit": limit})
        body, pace_seconds = _get(_RSS_URL.format(sub=sub, qs=qs))
        posts.extend(_parse_atom(body, query))
    return posts


def fetch_polymarket(tag_slug: str, limit: int = 25) -> list[Post]:
    """Prediction-market events under a single Polymarket tag.

    Polymarket has no keyword search: `q` and `search` are confirmed live (see
    this package's CLAUDE.md) to be silently ignored -- `?q=energy`,
    `?search=energy` and even a nonsense query all return the identical
    unfiltered list with HTTP 200. `tag_slug` is the only parameter that
    genuinely filters, so this fetcher takes a tag rather than free text, and
    Polymarket contributes tag-level attention rather than a per-topic series.
    `query` is stamped with the tag slug used.

    The response is a bare JSON array, not a wrapped object. `id` is a string
    (e.g. `"2890"`) -- no int coercion. There is no canonical timestamp field;
    `startDate` is used, falling back to `createdAt` (not `endDate` or
    `closedTime`, which are future-dated). There is no `url` field, so one is
    built from `slug`.

    Polymarket has no per-event score field, so `score` stays None. It does
    carry a genuine top-level `commentCount`, used for `num_comments` rather
    than left None -- unlike `score`, this is a real, confirmed-live metric."""
    qs = urlencode({"limit": limit, "active": "true", "tag_slug": tag_slug})
    body, _ = _get(_POLYMARKET_URL.format(qs=qs))
    rows = json.loads(body)

    posts: list[Post] = []
    for row in rows:
        slug = row.get("slug")
        title = (row.get("title") or "").strip()
        event_id = row.get("id")
        if not slug or not title or not event_id:
            continue
        num_comments = row.get("commentCount")
        posts.append(
            Post(
                post_id=str(event_id),
                url=f"https://polymarket.com/event/{slug}",
                title=title,
                ts=pd.Timestamp(row.get("startDate") or row.get("createdAt")),
                platform="polymarket",
                query=tag_slug,
                score=None,
                num_comments=num_comments if isinstance(num_comments, int) else None,
            )
        )
    return posts


def _get_tolerating_one_failure(url: str) -> bytes:
    """Single request with exactly one retry, after a short fixed pause, on
    ANY non-2xx -- not just 429. Task 0 saw one unexplained HTTP 403 with an
    empty body sandwiched between clean 200s, with no explanatory header;
    five immediate retries afterwards all succeeded. A lone failure is not
    proof StockTwits is blocking us, so it must not be treated that way and
    must not silently produce an empty list. If the retry also fails, the
    real status code is logged and the error re-raised."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()  # type: ignore[no-any-return]
    except HTTPError as exc:
        _sleep(_STOCKTWITS_RETRY_PAUSE_SECONDS)
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as retried:
                return retried.read()  # type: ignore[no-any-return]
        except HTTPError as retry_exc:
            logger.error(
                "StockTwits request failed twice in a row (status %s, then %s "
                "on retry): %s",
                exc.code,
                retry_exc.code,
                url,
            )
            raise


def fetch_stocktwits(symbol: str, limit: int = 25) -> list[Post]:
    """Public symbol stream. `symbol` is a ticker, so this feeds Set A only.

    The response is a wrapped JSON object; messages live under `messages`.
    `id` is an int, `created_at` is ISO-8601. There is no permalink field on a
    message itself, so a URL is constructed from `user.username` + `id`
    (falling back to an id-only URL if `username` is somehow absent).

    StockTwits exposes no numeric score and no comment count on a message, so
    both `score` and `num_comments` stay None -- never a fabricated 0."""
    body = _get_tolerating_one_failure(_STOCKTWITS_URL.format(symbol=symbol))
    payload = json.loads(body)
    messages = payload.get("messages", [])[:limit]

    posts: list[Post] = []
    for message in messages:
        text = (message.get("body") or "").strip()
        message_id = message.get("id")
        if not text or message_id is None:
            continue
        username = (message.get("user") or {}).get("username")
        url = (
            f"https://stocktwits.com/{username}/message/{message_id}"
            if username
            else f"https://stocktwits.com/message/{message_id}"
        )
        posts.append(
            Post(
                post_id=str(message_id),
                url=url,
                title=text,
                ts=pd.Timestamp(message["created_at"]),
                platform="stocktwits",
                query=symbol,
                score=None,
                num_comments=None,
            )
        )
    return posts
