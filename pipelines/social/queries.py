"""Query universe for Spec 29's self-hosted social sentiment.

Two deliberately separate sets. Set A (TICKER_QUERIES) exists solely to give an
apples-to-apples overlap against Spec 17's Adanos series for the same ticker,
platform and day -- it is frozen, not re-ranked, because a set that silently
re-ranks would break the continuity of every social.* series it names. Set B
(TOPIC_QUERIES) is the coverage Adanos cannot express at all: commodity and
geopolitical topics, searched by query rather than by ticker.

Same small-reference-table-as-Python precedent as pipelines/news/queries.py.

Reddit's own fetch strategy (subreddit list vs. site-wide search) was Task 2's
decision, gated on probing whether site-wide search works within Reddit's
~1-request-per-60-seconds unauthenticated rate limit. Confirmed live it does
NOT: `https://www.reddit.com/search.rss?q=Henry+Hub&sort=new&limit=25` returns
entries, but they are not filtered by the query at all -- see this package's
NOTES.md for the two probes that established this. Subreddit search is kept,
narrowed to two subreddits (not the brief's five) to stay inside the rate
limit."""

from __future__ import annotations

import re
from typing import TypedDict


class TopicQuery(TypedDict):
    slug: str
    query: str
    commodity: str
    theme: str


PLATFORMS: list[str] = ["reddit", "polymarket", "stocktwits"]

# Task 2's choice, not five: site-wide Reddit search ignores the query entirely
# (confirmed live, see pipelines/social/NOTES.md), so per-subreddit search.rss
# is kept, but narrowed from the brief's five subreddits to two -- at Reddit's
# confirmed ~1-request-per-60-seconds unauthenticated limit, every extra
# subreddit multiplies the pull's wall-clock time directly.
SUBREDDITS: list[str] = ["energy", "oil"]

# Frozen 2026-09-06 by mean adanos.reddit.*.buzz_score over the single day of
# Adanos data present in the lake (2026-09-03) -- not a history, one pull of
# 57 tickers, 45 of them with nonzero buzz. Deliberately never recomputed --
# see this package's NOTES.md.
TICKER_QUERIES: list[str] = [
    "CVX", "XOM", "USO", "BP", "CCJ", "XLE",
    "COP", "SU", "SLB", "PBR", "NEE", "CNQ",
]

TOPIC_QUERIES: list[TopicQuery] = [
    {"slug": "brent", "query": "Brent crude", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "wti", "query": "WTI crude", "commodity": "crude", "theme": "benchmarks"},
    {
        "slug": "urals_discount",
        "query": "Urals discount",
        "commodity": "crude",
        "theme": "benchmarks",
    },
    {"slug": "dubai_swap", "query": "Dubai swap", "commodity": "crude", "theme": "benchmarks"},
    {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "jkm", "query": "JKM LNG", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "ttf", "query": "TTF gas", "commodity": "gas", "theme": "gas_lng"},
    {"slug": "lng_cargo", "query": "LNG cargo", "commodity": "gas", "theme": "gas_lng"},
    {
        "slug": "strait_of_hormuz",
        "query": "Strait of Hormuz",
        "commodity": "crude",
        "theme": "chokepoints",
    },
    {
        "slug": "red_sea_shipping",
        "query": "Red Sea shipping",
        "commodity": "crude",
        "theme": "chokepoints",
    },
    {
        "slug": "bab_el_mandeb",
        "query": "Bab el-Mandeb",
        "commodity": "crude",
        "theme": "chokepoints",
    },
    {"slug": "nnpc", "query": "NNPC Nigeria oil", "commodity": "crude", "theme": "opec_producers"},
    {
        "slug": "kurdistan_oil_exports",
        "query": "Kurdistan oil exports",
        "commodity": "crude",
        "theme": "opec_producers",
    },
    {
        "slug": "libya_noc",
        "query": "Libya NOC oil",
        "commodity": "crude",
        "theme": "opec_producers",
    },
    {
        "slug": "pdvsa",
        "query": "PDVSA Venezuela oil",
        "commodity": "crude",
        "theme": "opec_producers",
    },
    {"slug": "crack_spread", "query": "crack spread", "commodity": "products", "theme": "refining"},
    {
        "slug": "refinery_outage",
        "query": "refinery outage",
        "commodity": "products",
        "theme": "refining",
    },
]


def slugify(text: str) -> str:
    """The fixed, permanent slug rule (Spec 29). Series IDs built from these are
    permanent, so this rule must never change: lower-case, every run of
    non-alphanumeric characters becomes a single underscore, strip the ends."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
