"""Self-hosted social fetchers (Spec 29). Adapted from TauricResearch/TradingAgents
(Apache-2.0) -- see this package's NOTES.md for the upstream commit. Upstream's
public fetchers return prompt-ready prose and its typed layer is underscore-private,
so the request handling is adapted here and canonical typed rows are returned instead.

Reddit needs no API key. Site-wide search (`www.reddit.com/search.rss`) was probed
live and confirmed NOT to filter by query at all -- see this package's NOTES.md for
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

import time
import xml.etree.ElementTree as ET
from email.message import Message
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
# Reddit's own confirmed-live pace: ~1 unauthenticated request per 60 seconds.
# Used whenever a response carries no X-Ratelimit-Reset header to read instead.
_DEFAULT_PACE_SECONDS = 60.0

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
