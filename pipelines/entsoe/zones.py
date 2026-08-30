"""Shared zone/border lists for pipelines/entsoe's pull scripts — the full bidding-zone
list from specs/04_entsoe-eu-power.md's Data sources section (all 13 confirmed live against
entsoe.mappings.Area, see pipelines/entsoe/NOTES.md)."""

from __future__ import annotations

ZONES = [
    "DE_LU",
    "FR",
    "NL",
    "BE",
    "AT",
    "ES",
    "IT_NORD",
    "PL",
    "NO_2",
    "SE_4",
    "DK_1",
    "IE_SEM",
    "GB",
]

# (from_zone, to_zone) — real, well-known interconnectors among the zones above. Not
# exhaustive (many more real borders exist between these 13 zones); this is a
# representative set past the spec's >=8-borders Definition of Done, confirmed live
# during Session B (see pipelines/entsoe/NOTES.md).
BORDERS = [
    ("DE_LU", "FR"),
    ("DE_LU", "NL"),
    ("DE_LU", "BE"),
    ("DE_LU", "AT"),
    ("DE_LU", "PL"),
    ("DE_LU", "DK_1"),
    ("FR", "ES"),
    ("FR", "GB"),
    ("NL", "GB"),
    ("IE_SEM", "GB"),
    ("NO_2", "DK_1"),
    ("SE_4", "DK_1"),
]
