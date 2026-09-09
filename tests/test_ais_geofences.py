from __future__ import annotations

import pytest
from pipelines.ais.geofences import (
    ANCHORAGES,
    CHOKEPOINTS,
    REGIONS,
    Region,
    region_for,
    subscription_boxes,
)


def test_every_region_key_is_unique() -> None:
    # The key names a raw-file partition and, later, a derived series id -- a duplicate
    # would silently merge two waterways' traffic into one count.
    keys = [r.key for r in REGIONS]
    assert len(set(keys)) == len(keys)


def test_a_transposed_box_is_rejected_rather_than_silently_matching_nothing() -> None:
    # aisstream accepts any box, so a swapped corner pair subscribes successfully and
    # then never yields a message -- indistinguishable from a quiet waterway.
    with pytest.raises(ValueError, match="south"):
        Region("bad", "Bad", "chokepoint", 27.0, 54.0, 25.0, 57.0)
    with pytest.raises(ValueError, match="west"):
        Region("bad", "Bad", "chokepoint", 25.0, 57.0, 27.0, 54.0)


@pytest.mark.parametrize(
    ("key", "lat", "lon"),
    [
        # Hand-placed points in real shipping lanes, checked against the named waterway.
        ("hormuz", 26.57, 56.25),  # mid-strait, off Bandar Abbas
        ("suez", 29.95, 32.55),  # Great Bitter Lake
        ("bab_el_mandeb", 12.58, 43.33),  # the narrows off Perim
        ("malacca", 1.27, 103.85),  # Singapore Strait eastbound lane
        ("bosphorus", 41.12, 29.06),  # mid-Bosphorus
        ("panama", 9.28, -79.92),  # Caribbean approach off Colón
        ("danish_straits", 55.68, 12.65),  # the Sound off Copenhagen
        ("good_hope", -34.36, 18.47),  # off Cape Point
    ],
)
def test_a_real_point_in_each_chokepoint_falls_inside_its_box(
    key: str, lat: float, lon: float
) -> None:
    region = next(r for r in CHOKEPOINTS if r.key == key)
    assert region.contains(lat, lon), f"{key} box excludes a point in its own waterway"


def test_a_point_in_the_north_atlantic_is_in_no_region() -> None:
    assert region_for(45.0, -30.0) is None


def test_overlapping_boxes_resolve_to_the_chokepoint_first() -> None:
    # Linggi's anchorage sits inside the Malacca box. region_for returns the first match
    # in REGIONS order, and chokepoints come first -- documented behaviour, asserted so a
    # reordering of the tuples cannot change it unnoticed.
    linggi = next(r for r in ANCHORAGES if r.key == "linggi")
    lat = (linggi.south + linggi.north) / 2
    lon = (linggi.west + linggi.east) / 2

    assert linggi.contains(lat, lon)
    found = region_for(lat, lon)
    assert found is not None
    assert found.key == "malacca"


def test_fujairah_lies_outside_the_hormuz_box_as_it_does_in_reality() -> None:
    # Not an oversight in the boxes: Fujairah is on the Gulf of Oman, *south* of the
    # strait, which is exactly why it matters -- it is the bunkering and storage anchorage
    # vessels use without entering Hormuz. A box that swallowed it would count anchored
    # tonnage as strait traffic.
    fujairah = next(r for r in ANCHORAGES if r.key == "fujairah")
    hormuz = next(r for r in CHOKEPOINTS if r.key == "hormuz")
    lat = (fujairah.south + fujairah.north) / 2
    lon = (fujairah.west + fujairah.east) / 2

    assert not hormuz.contains(lat, lon)
    found = region_for(lat, lon)
    assert found is not None
    assert found.key == "fujairah"


def test_subscription_boxes_are_lat_first_pairs_of_corners() -> None:
    # aisstream.io expects [[lat, lon], [lat, lon]]. Sending lon first is accepted and
    # yields nothing, which is the failure this shape check exists to prevent.
    boxes = subscription_boxes()

    assert len(boxes) == len(REGIONS)
    for box in boxes:
        assert len(box) == 2
        (south, west), (north, east) = box
        assert -90 <= south < north <= 90, "latitudes must come first and be ordered"
        assert -180 <= west < east <= 180
