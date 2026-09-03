from __future__ import annotations

from apps.dashboard.components.geo_centroids import centroid_for


def test_centroid_for_resolves_a_2letter_iso_code() -> None:
    assert centroid_for("US") == (39.8, -98.6)


def test_centroid_for_resolves_a_full_country_name() -> None:
    assert centroid_for("Netherlands") == (52.1, 5.3)


def test_centroid_for_returns_none_for_empty_geo() -> None:
    assert centroid_for("") is None


def test_centroid_for_returns_none_for_an_unmatched_geo() -> None:
    assert centroid_for("Not A Real Country") is None
