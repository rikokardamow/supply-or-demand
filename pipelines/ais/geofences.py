"""Monitored regions: chokepoints and floating-storage anchorages (Spec 11).

**Hand-curated bounding boxes, not survey data.** Each box is a generous rectangle drawn
around the waterway or anchorage rather than its legal or hydrographic boundary — wide
enough that a vessel transiting is seen on both approaches, which is what transit
detection needs, and loose enough that a box is never mistaken for a precise polygon.
Spec 11 calls for shapely polygons and a gate line per chokepoint for crossing detection;
that is Session D's work. Session A needs only the subscription boxes.

Coordinates are `(south, west)` and `(north, east)` corners in decimal degrees, WGS 84 —
the order aisstream.io's `BoundingBoxes` field expects, which is `[[lat, lon], [lat, lon]]`
with latitude first.

Coverage honesty (Spec 11's own clause): aisstream.io is a terrestrial receiver network.
Coastal and chokepoint coverage is good; open ocean is patchy. Every series derived from
this is a proxy and must be labelled as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

RegionKind = Literal["chokepoint", "anchorage"]


@dataclass(frozen=True)
class Region:
    """One monitored box. `south`/`north` are latitudes, `west`/`east` longitudes."""

    key: str
    label: str
    kind: RegionKind
    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        # A transposed corner pair produces a box that silently matches nothing, and the
        # subscription would still be accepted -- so it is caught here instead.
        if self.south >= self.north:
            raise ValueError(f"{self.key}: south {self.south} must be below north {self.north}")
        if self.west >= self.east:
            raise ValueError(f"{self.key}: west {self.west} must be west of east {self.east}")

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def as_bounding_box(self) -> list[list[float]]:
        """aisstream.io's own shape: `[[lat, lon], [lat, lon]]`, latitude first."""
        return [[self.south, self.west], [self.north, self.east]]


# The six chokepoints Spec 11 names, plus the Danish Straits and the Cape. Boxes are
# deliberately wider than the waterway so a transit is seen approaching and leaving.
CHOKEPOINTS: Final[tuple[Region, ...]] = (
    Region("hormuz", "Strait of Hormuz", "chokepoint", 25.5, 54.5, 27.2, 57.5),
    Region("suez", "Suez Canal and Gulf of Suez", "chokepoint", 27.0, 32.3, 31.5, 34.0),
    Region("bab_el_mandeb", "Bab el-Mandeb", "chokepoint", 11.5, 42.0, 13.5, 44.5),
    Region("malacca", "Malacca and Singapore Strait", "chokepoint", 0.5, 100.0, 4.5, 105.5),
    Region("bosphorus", "Bosphorus", "chokepoint", 40.8, 28.5, 41.4, 29.5),
    Region("panama", "Panama Canal approaches", "chokepoint", 8.0, -80.5, 9.6, -79.0),
    Region("danish_straits", "Danish Straits", "chokepoint", 54.5, 10.0, 56.5, 13.0),
    Region("good_hope", "Cape of Good Hope", "chokepoint", -36.5, 15.0, -33.0, 22.0),
)

# Anchorages where laden tankers sit: the floating-storage proxy's raw material.
ANCHORAGES: Final[tuple[Region, ...]] = (
    Region("fujairah", "Fujairah anchorage", "anchorage", 24.8, 56.2, 25.6, 56.7),
    Region("singapore_opl", "Singapore OPL", "anchorage", 0.9, 103.4, 1.5, 104.5),
    Region("rotterdam", "Rotterdam approaches", "anchorage", 51.8, 3.4, 52.2, 4.4),
    Region("gibraltar", "Gibraltar and Ceuta", "anchorage", 35.7, -5.9, 36.3, -5.0),
    Region("malta", "Malta and Kalamata", "anchorage", 35.6, 14.1, 36.4, 15.0),
    Region("linggi", "Off Malaysia (Linggi)", "anchorage", 1.9, 101.5, 2.6, 102.4),
)

REGIONS: Final[tuple[Region, ...]] = CHOKEPOINTS + ANCHORAGES


def subscription_boxes() -> list[list[list[float]]]:
    """Every monitored box, in aisstream.io's `BoundingBoxes` shape."""
    return [region.as_bounding_box() for region in REGIONS]


def region_for(lat: float, lon: float) -> Region | None:
    """The first region containing this point, or None.

    Boxes can overlap by construction -- Fujairah sits inside the Hormuz box, and Linggi
    inside Malacca -- so this returns the first match in `REGIONS` order, which puts
    chokepoints first. Anything needing every containing region should iterate `REGIONS`
    itself rather than relying on this.
    """
    for region in REGIONS:
        if region.contains(lat, lon):
            return region
    return None
