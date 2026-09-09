"""Shared zone/border lists for pipelines/entsoe's pull scripts — the full bidding-zone
list from specs/04_entsoe-eu-power.md's Data sources section (all 13 confirmed live against
entsoe.mappings.Area, see pipelines/entsoe/CLAUDE.md)."""

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

# (from_zone, to_zone) — real interconnectors among the zones above. Not exhaustive (many
# more real borders exist between these 13 zones); this is a representative set past the
# spec's >=8-borders Definition of Done.
#
# "Confirmed live" used to be claimed for this whole list and was not true of all of it.
# SE_4 -> DK_1 was never a real border: SE4's Danish neighbour is DK2 across the Öresund,
# and the Sweden-to-DK1 link (Konti-Skan) lands in SE3, which is not a configured zone. It
# returned HTTP 400 on one run and zero rows with no error on the next — ENTSO-E answering
# and saying there is nothing there. Replaced 2026-09-09 with SE_4's two interconnectors
# that DO reach configured zones, both verified live the same day over a 2-day window:
# Baltic Cable (SE_4 <-> DE_LU, 192 rows) and SwePol (SE_4 <-> PL, 192 rows).
#
# IE_SEM -> GB is a real link (East-West and Moyle) but the Transparency Platform serves
# nothing for it — zero rows, no error, verified the same day. GB itself is not the
# problem: FR -> GB and NL -> GB both return data. Kept rather than removed, because the
# border is genuine and the gap is on ENTSO-E's side; `pull_flows` already tolerates a
# border that yields nothing. Do not "fix" it by retrying — it has been checked.
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
    ("SE_4", "DE_LU"),
    ("SE_4", "PL"),
]
