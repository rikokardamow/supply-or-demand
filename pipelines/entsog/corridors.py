"""Hand-curated corridor definitions. Every pointKey below was found live via the
operator-point directory (GET /operatorpointdirections.json), not guessed — see
pipelines/entsog/NOTES.md for the full corridor->pointKey table and how each was found.
validate_corridors() cross-checks every one against the (cached) directory and fails loudly
on a stale/mistyped key, per the spec's "fail loudly otherwise" instruction."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PointSpec:
    point_key: str
    direction_key: str
    from_node: str
    to_node: str


CORRIDORS: dict[str, list[PointSpec]] = {
    "NO_EXPORTS": [
        PointSpec("ITP-00105", "entry", "NO", "DE"),  # Emden EPT (Thyssengas)
        PointSpec("ITP-00075", "entry", "NO", "DE"),  # Emden NPT (Thyssengas)
        PointSpec("ITP-00126", "entry", "NO", "DE"),  # Dornum (Open Grid Europe)
        PointSpec("ITP-00106", "entry", "NO", "BE"),  # Zeebrugge ZPT
        PointSpec("ITP-00519", "entry", "NO", "FR"),  # Dunkerque DKB
        PointSpec("ITP-00091", "entry", "NO", "GB"),  # Easington
        PointSpec("ITP-00022", "entry", "NO", "GB"),  # St. Fergus
    ],
    "TAP": [
        # Origin is Azerbaijan via Georgia/Turkey/Greece/Albania — no single ISO country
        # is clearly "the" upstream node, so from_node names the pipeline itself.
        PointSpec("ITP-00008", "entry", "TAP", "IT"),  # Melendugno
    ],
    "TURKSTREAM_EU": [
        PointSpec("ITP-00549", "entry", "TURKSTREAM", "BG"),  # Strandzha 2 / Malkoclar
    ],
    "ES_FR": [
        PointSpec("ITP-00304", "entry", "FR", "ES"),  # VIP Pirineos (Enagas side)
    ],
    "UK_BE": [
        PointSpec("ITP-00005", "entry", "BE", "GB"),  # Bacton (IUK)
    ],
    "GB_IE": [
        PointSpec("ITP-00495", "entry", "GB", "IE"),  # Moffat (IE)
    ],
}


def validate_corridors(directory: pd.DataFrame) -> None:
    valid_pairs = set(zip(directory["pointKey"], directory["directionKey"], strict=False))

    for corridor_name, points in CORRIDORS.items():
        for point in points:
            if (point.point_key, point.direction_key) not in valid_pairs:
                raise ValueError(
                    f"corridors.py: {corridor_name}'s point {point.point_key} "
                    f"({point.direction_key}) not found in the ENTSOG directory — "
                    "stale or mistyped pointKey. Re-check pipelines/entsog/directory.py's "
                    "cached data or the pointKey itself."
                )
