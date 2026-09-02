"""Session B's tagging engine: derives `tags`/`geo`/`severity` purely from an article's
own headline text via regex/keyword dictionaries -- replaces Session A's placeholder
tagging (`tags=[event_type]` straight from the query dictionary, `severity=1` fixed).
`commodity` is untouched here -- it still comes from the query dictionary
(pipelines/news/queries.py), which is a reliable enough signal on its own.

Headline-derived geo takes precedence over GDELT's own `sourcecountry` field
deliberately: `sourcecountry` is the *publisher's* country, not necessarily the
event's location (e.g. a US wire-service article about a Rotterdam refinery fire
would have sourcecountry="United States", not "Netherlands") -- see NOTES.md."""

from __future__ import annotations

import re

# tag -> keyword patterns (case-insensitive, word-boundary matched against the
# headline). Multiple tags can match the same headline.
TAG_KEYWORDS: dict[str, list[str]] = {
    "outage": ["outage", "shutdown", "halt", "fire", "explosion", "blast", "force majeure"],
    "strike": ["strike", "walkout"],
    "sanctions": ["sanction", "embargo", "price cap"],
    "opec": ["opec", "quota"],
    "geopolitics": ["seized", "blocked", "attack", "tanker"],
}

# Per the spec's own literal tiers: 3 = force majeure/explosion/embargo, 2 =
# outage/strike, 1 = general. "fire"/"blast" are grouped into tier 3 alongside
# "explosion" (the same kind of physical-incident severity, not routine downtime) --
# needed for the spec's own "refinery fire ... severity 2+" acceptance case, since a
# bare "fire" isn't literally one of the 3 named tier-3 words but is at least as severe.
SEVERITY_3_KEYWORDS = ["force majeure", "explosion", "embargo", "fire", "blast"]
SEVERITY_2_KEYWORDS = ["outage", "shutdown", "halt", "strike", "walkout"]

# keyword -> ISO-3166 alpha-2 code, for events named by city/region rather than
# country in the headline. Deliberately small (Session B scope) -- major oil/gas hubs
# and countries that show up often in this pipeline's own curated queries
# (pipelines/news/queries.py). Not a general-purpose gazetteer.
GEO_KEYWORDS: dict[str, str] = {
    "rotterdam": "NL",
    "amsterdam": "NL",
    "antwerp": "BE",
    "houston": "US",
    "cushing": "US",
    "gulf of mexico": "US",
    "ras tanura": "SA",
    "saudi arabia": "SA",
    "yanbu": "SA",
    "fujairah": "AE",
    "strait of hormuz": "IR",
    "basra": "IQ",
    "iraq": "IQ",
    "iran": "IR",
    "russia": "RU",
    "novorossiysk": "RU",
    "venezuela": "VE",
    "nigeria": "NG",
    "libya": "LY",
    "singapore": "SG",
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Only the start of each keyword is boundary-anchored (`\\b`, not `\\bkw\\b`) --
    confirmed live by a failing test: a trailing `\\b` rejects simple plural/inflected
    forms like "sanctions" (no word boundary between "sanction" and its "-s"), while
    still correctly rejecting a keyword appearing mid-word (e.g. "halt" inside
    "asphalt" has no boundary immediately before it either)."""
    return any(re.search(rf"\b{re.escape(kw)}", text) for kw in keywords)


def extract_tags(headline: str) -> list[str]:
    text = headline.lower()
    return [tag for tag, keywords in TAG_KEYWORDS.items() if _contains_any(text, keywords)]


def extract_severity(headline: str) -> int:
    text = headline.lower()
    if _contains_any(text, SEVERITY_3_KEYWORDS):
        return 3
    if _contains_any(text, SEVERITY_2_KEYWORDS):
        return 2
    return 1


def extract_geo(headline: str, fallback: str = "") -> str:
    """Returns a 2-letter code when a known place-name keyword is found in the
    headline, else `fallback` as-is (typically GDELT's own `sourcecountry`, a full
    country name, not a code -- a known, documented format inconsistency, not a bug;
    see NOTES.md)."""
    text = headline.lower()
    for keyword, code in GEO_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}", text):
            return code
    return fallback
