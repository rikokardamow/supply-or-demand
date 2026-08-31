"""Well-known commercial trading hubs / zones for each ISO's LMP pull, confirmed live
(Spec 05 Session B) -- not every node. See NOTES.md for how these were found."""

from __future__ import annotations

CAISO_HUBS = [
    "TH_NP15_GEN-APND",
    "TH_SP15_GEN-APND",
    "TH_ZP26_GEN-APND",
]

# NYISO's own load zones are already zone-level (not thousands of individual
# nodes like ERCOT/MISO), so every real zone is used rather than curating a
# subset -- confirmed live via get_lmp(locations="ALL"). Excludes external
# interface/proxy ties (H Q, NPX, O H, PJM) that aren't NY load zones.
NYISO_ZONES = [
    "CAPITL",
    "CENTRL",
    "DUNWOD",
    "GENESE",
    "HUD VL",
    "LONGIL",
    "MHK VL",
    "MILLWD",
    "N.Y.C.",
    "NORTH",
    "WEST",
]

HUBS: dict[str, list[str]] = {"CAISO": CAISO_HUBS, "NYISO": NYISO_ZONES}
