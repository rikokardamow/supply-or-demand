"""Static country-centroid lookup for the news world map (Spec 09 redesign).

No live geocoding API is used here -- `restcountries.com`'s free v3 API is confirmed
dead (every query returns HTTP 200 with a body saying the API version is deprecated,
a "200 that lies" case). Country centroids are stable geographic facts, not a live
"don't guess" business dataset, so a small hand-maintained table is the right call
here, matching this project's own `pipelines/weather/cities.csv` precedent.

`events.geo` (see `pipelines/news/tagging.py::GEO_KEYWORDS`/`extract_geo`) holds EITHER
a 2-letter ISO code (when a headline keyword matched) OR a full country name (GDELT's/
Guardian's own publisher-country fallback, e.g. "United States", "South Korea") -- both
forms are confirmed live in the real lake, so this table's keys cover both. Values are
approximate country centroids (roughly the population-weighted centre or capital
region, not the precise geographic centre), which is standard practice for a
country-level world map; do not treat them as precise.
"""

from __future__ import annotations

# (lat, lon)
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    # --- 2-letter ISO codes GEO_KEYWORDS can produce ---
    "NL": (52.1, 5.3),
    "BE": (50.6, 4.5),
    "US": (39.8, -98.6),
    "SA": (24.0, 45.0),
    "AE": (23.8, 54.0),
    "IR": (32.4, 53.7),
    "IQ": (33.2, 43.7),
    "RU": (61.5, 105.3),
    "VE": (6.4, -66.6),
    "NG": (9.1, 8.7),
    "LY": (26.3, 17.2),
    "SG": (1.35, 103.8),
    # --- Full country names (GDELT/Guardian publisher-country fallback) ---
    "Afghanistan": (33.9, 67.7),
    "Albania": (41.2, 20.2),
    "Algeria": (28.0, 2.6),
    "Argentina": (-38.4, -63.6),
    "Australia": (-25.3, 133.8),
    "Austria": (47.5, 14.6),
    "Azerbaijan": (40.1, 47.6),
    "Bahamas": (25.0, -77.4),
    "Bahrain": (26.0, 50.6),
    "Bangladesh": (23.7, 90.4),
    "Belgium": (50.6, 4.5),
    "Belize": (17.2, -88.5),
    "Bolivia": (-16.3, -63.6),
    "Brazil": (-14.2, -51.9),
    "Canada": (56.1, -106.3),
    "China": (35.9, 104.2),
    "Colombia": (4.6, -74.3),
    "Congo": (-0.2, 15.8),
    "Croatia": (45.1, 15.2),
    "Cuba": (21.5, -77.8),
    "Cyprus": (35.1, 33.4),
    "Czech Republic": (49.8, 15.5),
    "Denmark": (56.3, 9.5),
    "Dominican Republic": (18.7, -70.2),
    "Egypt": (26.8, 30.8),
    "Estonia": (58.6, 25.0),
    "Finland": (61.9, 25.7),
    "France": (46.6, 2.2),
    "Germany": (51.2, 10.5),
    "Greece": (39.1, 21.8),
    "Guatemala": (15.8, -90.2),
    "Honduras": (15.2, -86.2),
    "Hong Kong": (22.3, 114.2),
    "Hungary": (47.2, 19.5),
    "India": (20.6, 79.0),
    "Indonesia": (-0.8, 113.9),
    "Iran": (32.4, 53.7),
    "Iraq": (33.2, 43.7),
    "Ireland": (53.4, -8.2),
    "Israel": (31.0, 34.8),
    "Italy": (41.9, 12.6),
    "Jamaica": (18.1, -77.3),
    "Japan": (36.2, 138.3),
    "Jordan": (30.6, 36.2),
    "Kazakhstan": (48.0, 66.9),
    "Kuwait": (29.3, 47.5),
    "Latvia": (56.9, 24.6),
    "Libya": (26.3, 17.2),
    "Macedonia": (41.6, 21.7),
    "Madagascar": (-18.8, 46.9),
    "Malaysia": (4.2, 101.9),
    "Malta": (35.9, 14.4),
    "Mauritania": (21.0, -10.9),
    "Mexico": (23.6, -102.5),
    "Morocco": (31.8, -7.1),
    "New Zealand": (-40.9, 174.9),
    "Niger": (17.6, 8.1),
    "Nigeria": (9.1, 8.7),
    "Norway": (60.5, 8.5),
    "Oman": (21.5, 55.9),
    "Pakistan": (30.4, 69.3),
    "Paraguay": (-23.4, -58.4),
    "Peru": (-9.2, -75.0),
    "Philippines": (12.9, 121.8),
    "Poland": (51.9, 19.1),
    "Portugal": (39.4, -8.2),
    "Qatar": (25.4, 51.2),
    "Romania": (45.9, 25.0),
    "Russia": (61.5, 105.3),
    "Saudi Arabia": (24.0, 45.0),
    "Serbia": (44.0, 21.0),
    "Singapore": (1.35, 103.8),
    "Slovak Republic": (48.7, 19.7),
    "Slovakia": (48.7, 19.7),
    "Somalia": (5.2, 46.2),
    "South Africa": (-30.6, 22.9),
    "South Korea": (35.9, 127.8),
    "Spain": (40.5, -3.7),
    "Sri Lanka": (7.9, 80.8),
    "Switzerland": (46.8, 8.2),
    "Syria": (34.8, 38.997),
    "Taiwan": (23.7, 121.0),
    "Thailand": (15.9, 101.0),
    "Trinidad and Tobago": (10.7, -61.2),
    "Turkey": (38.96, 35.24),
    "Ukraine": (48.4, 31.2),
    "United Arab Emirates": (23.4, 53.8),
    "United Kingdom": (55.4, -3.4),
    "United States": (39.8, -98.6),
    "Uruguay": (-32.5, -55.8),
    "Venezuela": (6.4, -66.6),
    "Vietnam": (14.1, 108.3),
    "Yemen": (15.6, 48.5),
    # --- Additional broad global coverage (not yet seen in the lake, future-proofing) ---
    "Angola": (-11.2, 17.9),
    "Bulgaria": (42.7, 25.5),
    "Chad": (15.5, 18.7),
    "Chile": (-35.7, -71.5),
    "Ecuador": (-1.8, -78.2),
    "Ethiopia": (9.1, 40.5),
    "Gabon": (-0.8, 11.6),
    "Ghana": (7.9, -1.0),
    "Kenya": (-0.02, 37.9),
    "Kosovo": (42.6, 20.9),
    "Kyrgyzstan": (41.2, 74.8),
    "Lebanon": (33.9, 35.9),
    "Lithuania": (55.2, 23.9),
    "Luxembourg": (49.8, 6.1),
    "Mozambique": (-18.7, 35.5),
    "Myanmar": (21.9, 95.96),
    "Netherlands": (52.1, 5.3),
    "North Korea": (40.3, 127.5),
    "Panama": (8.5, -80.8),
    "Palestine": (31.9, 35.2),
    "Senegal": (14.5, -14.5),
    "Slovenia": (46.1, 14.8),
    "Sudan": (12.9, 30.2),
    "Sweden": (60.1, 18.6),
    "Tunisia": (33.9, 9.6),
    "Turkmenistan": (38.97, 59.6),
    "Uganda": (1.4, 32.3),
    "Uzbekistan": (41.4, 64.6),
    "Zambia": (-13.1, 27.9),
    "Zimbabwe": (-19.0, 29.2),
}


def centroid_for(geo: str) -> tuple[float, float] | None:
    """Resolves a `events.geo` value to (lat, lon). Returns None for an unmatched or
    empty geo -- the caller (news_map.py) excludes that event from the map's markers
    only; it stays reachable in the text feed under a "no location" catch-all, per the
    approved plan."""
    if not geo:
        return None
    return COUNTRY_CENTROIDS.get(geo) or COUNTRY_CENTROIDS.get(geo.strip())
