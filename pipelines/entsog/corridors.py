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
    # Only needed where the directory lists more than one operator reporting real,
    # different values for the same point+direction (confirmed for ITP-00304 and
    # ITP-00008's nomination data — see pipelines/entsog/NOTES.md) — None elsewhere.
    operator_key: str | None = None


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
        # operator_key pins this to the receiving side (Snam Rete Gas/IT) — TAP AG's own
        # side reports real nomination values too (though not physical flow), which
        # would otherwise double-count nominations.
        PointSpec("ITP-00008", "entry", "TAP", "IT", operator_key="IT-TSO-0001"),
    ],
    "TURKSTREAM_EU": [
        PointSpec("ITP-00549", "entry", "TURKSTREAM", "BG"),  # Strandzha 2 / Malkoclar
    ],
    "ES_FR": [
        # operator_key pins this to the receiving side (Enagas/ES) — Terega's (FR) side
        # reports its own real, much smaller "entry" value for the same point+direction,
        # which would otherwise double-count both physical flow and nominations.
        PointSpec("ITP-00304", "entry", "FR", "ES", operator_key="ES-TSO-0006"),
    ],
    "UK_BE": [
        PointSpec("ITP-00005", "entry", "BE", "GB"),  # Bacton (IUK)
    ],
    "GB_IE": [
        PointSpec("ITP-00495", "entry", "GB", "IE"),  # Moffat (IE)
    ],
    "RU_UA_TRANSIT": [
        # May be zero/dormant (kept for history, per the spec) — Ukraine's own TSO
        # reports the receiving "entry" side; Gazprom's "exit" side has hasData=False
        # in the live directory, consistent with the receiving-side convention above.
        PointSpec("ITP-00184", "entry", "RU", "UA"),  # Sudzha
    ],
    "LNG_ENTRY": [
        # Ship-borne, not a single upstream country — from_node names the mode itself,
        # same convention as TAP/TURKSTREAM_EU above. One representative terminal per
        # major EU LNG-importing country (pointType == "LNG Entry point" in the
        # directory), not every terminal ENTSOG tracks.
        PointSpec("LNG-00027", "entry", "LNG", "NL"),  # Gate Terminal
        PointSpec("LNG-00017", "entry", "LNG", "BE"),  # Zeebrugge LNG
        PointSpec("LNG-00024", "entry", "LNG", "FR"),  # Montoir de Bretagne
        PointSpec("LNG-00029", "entry", "LNG", "FR"),  # Fos (Tonkin/Cavaou)
        PointSpec("LNG-00012", "entry", "LNG", "ES"),  # Barcelona
        PointSpec("LNG-00006", "entry", "LNG", "PL"),  # Świnoujście
        PointSpec("LNG-00004", "entry", "LNG", "IT"),  # OLT LNG / Livorno
        PointSpec("LNG-00026", "entry", "LNG", "PT"),  # Sines
    ],
}


def validate_corridors(directory: pd.DataFrame) -> None:
    valid_pairs = set(zip(directory["pointKey"], directory["directionKey"], strict=False))
    valid_operators_by_point = {
        point_key: set(rows["operatorKey"])
        for point_key, rows in directory.groupby("pointKey")
        if "operatorKey" in directory.columns
    }

    for corridor_name, points in CORRIDORS.items():
        for point in points:
            if (point.point_key, point.direction_key) not in valid_pairs:
                raise ValueError(
                    f"corridors.py: {corridor_name}'s point {point.point_key} "
                    f"({point.direction_key}) not found in the ENTSOG directory — "
                    "stale or mistyped pointKey. Re-check pipelines/entsog/directory.py's "
                    "cached data or the pointKey itself."
                )
            if (
                point.operator_key is not None
                and point.operator_key not in valid_operators_by_point.get(point.point_key, set())
            ):
                raise ValueError(
                    f"corridors.py: {corridor_name}'s point {point.point_key} pins "
                    f"operator_key={point.operator_key!r}, which isn't among the "
                    "operators the ENTSOG directory lists for that point — stale or "
                    "mistyped operatorKey."
                )
