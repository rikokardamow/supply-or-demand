"""Energy-relevance tagging, IMO extraction, and geo resolution for OFAC SDN rows.
Reuses `pipelines/news/tagging.py::_contains_any` directly rather than
reimplementing the same tiny regex helper (per specs/15_ofac-sanctions.md's own
"reuse this pattern, don't reimplement" instruction) -- it's generic (case-
insensitive, start-boundary-anchored keyword matching) and has no news-specific
coupling.

**Real gotcha, confirmed live**: `pipelines/ofac/client.py::fetch_sdn_csv` maps
OFAC's `-0-` null placeholder to Python `None` via `Series.map()` -- but pandas
silently converts a mapped `None` into a float `NaN` in the resulting column
(confirmed live: `type(mapped.iloc[0])` is `float`, not `NoneType`). `NaN` is
truthy in plain Python (`bool(float("nan"))` is `True`), so a bare `if not value`/
`value or default` guard silently fails to catch it and can crash downstream
(`str.strip()` on a float) or silently misbehave (`nan or ""` evaluates to `nan`,
not `""`). Every nullable-field check below uses `pd.isna()` explicitly instead."""

from __future__ import annotations

import re

import pandas as pd
from pipelines.news.tagging import _contains_any

# Real sanctioned energy entities/keywords, matched against name/remarks/programs.
ENERGY_KEYWORDS = [
    "tanker",
    "crude",
    "petroleum",
    "petrol",
    "oil",
    "gas",
    "lng",
    "refinery",
    "refining",
    "shipping",
    "pipeline",
    "energy",
    "rosneft",
    "gazprom",
    "lukoil",
    "pdvsa",
    "national iranian oil",
]

# Confirmed live: 1,525 of 1,540 real vessel rows (99%) have a matching IMO number
# in `remarks`, e.g. "Vessel Registration Identification IMO 7406784".
_IMO_PATTERN = re.compile(r"IMO\s+(\d{7})")

# Program-code prefix -> ISO-3166 alpha-2. Real program codes are frequently
# suffixed (e.g. "IRAN-EO13902", "IRAN-HR") -- a prefix check catches all variants
# of a given country without needing all 243 distinct real codes enumerated.
# "UKRAINE-EO136xx" programs target Russia's own actions re: Ukraine, so the
# geo-relevant country is Russia, not Ukraine -- deliberate, not an oversight.
PROGRAM_COUNTRY_PREFIXES: dict[str, str] = {
    "IRAN": "IR",
    "RUSSIA": "RU",
    "UKRAINE": "RU",
    "VENEZUELA": "VE",
    "CUBA": "CU",
    "BELARUS": "BY",
    "DPRK": "KP",
    "NICARAGUA": "NI",
    "BURMA": "MM",
    "IRAQ": "IQ",
    "SYRIA": "SY",
    "LIBYA": "LY",
    "SUDAN": "SD",
    "SOMALIA": "SO",
    "YEMEN": "YE",
    "ZIMBABWE": "ZW",
}

# Vess_flag is a real country *name* (e.g. "Cuba", "Panama") -- mapped to the same
# short-code convention this project already uses elsewhere (tagging.py's own
# GEO_KEYWORDS, geo_centroids.py). Not exhaustive -- only the flags actually seen
# live among real vessel rows plus a few likely others; an unmapped flag falls
# through to the program-prefix path instead of guessing.
VESS_FLAG_TO_GEO: dict[str, str] = {
    "cuba": "CU",
    "panama": "PA",
    "iran": "IR",
    "russia": "RU",
    "venezuela": "VE",
    "north korea": "KP",
    "syria": "SY",
    "liberia": "LR",
    "marshall islands": "MH",
    "hong kong": "HK",
    "china": "CN",
}


def extract_imo(remarks: str | None) -> str | None:
    if pd.isna(remarks):
        return None
    match = _IMO_PATTERN.search(remarks)
    return match.group(1) if match else None


def is_energy_related(
    name: str, remarks: str | None, programs: list[str], entity_type: str
) -> bool:
    """A sanctioned vessel is inherently shipping-relevant even when its cargo type
    isn't stated -- unconditionally True regardless of keyword match, per
    specs/15_ofac-sanctions.md."""
    if entity_type == "vessel":
        return True
    clean_remarks = "" if pd.isna(remarks) else remarks
    text = " ".join([name, clean_remarks, " ".join(programs)]).lower()
    return _contains_any(text, ENERGY_KEYWORDS)


def resolve_geo(programs: list[str], vess_flag: str | None) -> str:
    """Vessel rows prefer `vess_flag` (a concrete, real country) over program-derived
    geo when present. Many real programs (SDGT, NPWMD, GLOMAG, TCO, ...) are
    thematic, not country-specific -- returns "" rather than guessing when nothing
    resolves."""
    if not pd.isna(vess_flag):
        code = VESS_FLAG_TO_GEO.get(vess_flag.strip().lower())
        if code:
            return code

    for program in programs:
        upper = program.upper()
        for prefix, code in PROGRAM_COUNTRY_PREFIXES.items():
            if upper.startswith(prefix):
                return code

    return ""
