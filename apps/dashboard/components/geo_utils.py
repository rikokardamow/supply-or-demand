"""Shared scattergeo helpers for directional flow maps (padd_map.py, entsog_map.py)."""

from __future__ import annotations

import math


def bearing_degrees(orig_lat: float, orig_lon: float, dest_lat: float, dest_lon: float) -> float:
    """Flat-plane approximation (fine at these scales) matching Plotly's marker angle
    convention: 0 = pointing up/north, increasing clockwise."""
    dx = dest_lon - orig_lon
    dy = dest_lat - orig_lat
    return math.degrees(math.atan2(dx, dy))
