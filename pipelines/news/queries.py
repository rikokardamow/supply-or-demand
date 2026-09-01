"""Hand-curated GDELT query dictionary, per (commodity x event_type) -- same small-
reference-table precedent as pipelines/weather/cities.py / pipelines/opec_momr/quotas.csv,
kept as Python rather than CSV since each row needs a multi-clause boolean query string,
not tabular scalars. Each row's `commodity`/`event_type` double as Session A's own basic
tagging (see pipelines/news/events.py) -- the fuller regex/severity/geo-dictionary engine
is Session B's job. Kept to <=10 queries per the spec's own instruction."""

from __future__ import annotations

from typing import TypedDict


class QuerySpec(TypedDict):
    commodity: str
    event_type: str
    query: str


QUERIES: list[QuerySpec] = [
    {
        "commodity": "crude",
        "event_type": "outage",
        "query": '("refinery" OR "pipeline") AND (outage OR fire OR explosion OR "force majeure")',
    },
    {
        "commodity": "gas",
        "event_type": "supply",
        "query": "(LNG OR pipeline) AND (outage OR maintenance OR strike)",
    },
    {
        "commodity": "crude",
        "event_type": "sanctions",
        "query": '(sanction OR "price cap" OR embargo) AND (oil OR crude OR tanker)',
    },
    {
        "commodity": "crude",
        "event_type": "opec",
        "query": "OPEC AND (quota OR cut OR meeting)",
    },
    {
        "commodity": "power",
        "event_type": "outage",
        "query": "(power OR grid OR electricity) AND (outage OR blackout OR strike)",
    },
    {
        "commodity": "crude",
        "event_type": "geopolitics",
        "query": '(tanker OR "shipping lane" OR strait) AND (attack OR seized OR blocked)',
    },
]
