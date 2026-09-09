# Leaflet Maps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four Plotly map surfaces with Leaflet maps that read the design
tokens and return usable click state, retiring the `on_select` workaround in `news_map.py`.

**Architecture:** One `components/basemap.py` owns tiles, attribution, colour and
interaction defaults; each surface calls it. `st_folium` is always given an explicit
`returned_objects` allow-list, because every returned key that changes reruns the page —
and a rerun on these pages means re-reading the lake.

**Tech Stack:** Python 3.12, Streamlit 1.63, folium, streamlit-folium, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-leaflet-maps-design.md`

## Global Constraints

- Ships **after** `2026-09-06-ui-design-system.md`. `basemap.py` imports `core/design.py`, which that plan creates.
- Branch `design/ui-restyle-impl`, in the worktree at `<REPO_ROOT>\Documents\<REPO>.worktrees\ui-restyle`.
- **The worktree's `.venv` is a junction to the shared clone's.** Installing folium changes the peer session's environment too. Tell the peer before Task 1, and never run a bare `uv sync` — it prunes the dev extras and takes pytest/ruff/mypy with them. `uv sync --all-extras` (the repo's `make install`) is the restore.
- `uv` is not on the Git Bash PATH: run it from PowerShell, or fall back to `./.venv/Scripts/python.exe -m pip`.
- Out of scope: the cartopy anomaly maps on `08_weather`. They are matplotlib raster fields; Leaflet is the wrong tool.
- Tiles stay free and keyless. No Mapbox token.

## Verified API facts

Read from `streamlit_folium/__init__.py` on 2026-09-06 — not from memory. Do not
re-derive these:

```python
def st_folium(fig, key=None, height=700, width=500, returned_objects=None,
              zoom=None, center=None, feature_group_to_add=None,
              return_on_hover=False, use_container_width=False,
              layer_control=None, pixelated=False, debug=False,
              render=True, on_change=None, wrap_longitude=False)
```

- It can return **15** keys: `last_clicked`, `last_object_clicked`,
  `last_object_clicked_count`, `last_object_clicked_tooltip`,
  `last_object_clicked_popup`, `all_drawings`, `last_active_drawing`, `bounds`, `zoom`,
  `last_circle_radius`, `last_circle_polygon`, `selected_layers`, `selected_tags`,
  `last_geocoder_result`.
- `returned_objects` filters that set: `{k: v for k, v in _defaults.items() if returned_objects is None or k in returned_objects}`. `None` returns everything — including `bounds` and `zoom`, which change on every pan.
- `return_on_hover` defaults to `False`. Leave it there; hover belongs in a client-side folium `Tooltip`.
- **`st_folium` has its own `use_container_width` parameter.** This is NOT the deprecated `st.plotly_chart` / `st.dataframe` argument that `CLAUDE.md` bans. Passing it here is correct; do not "fix" it.

---

### Task 1: Dependencies and the shared basemap

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Create: `apps/dashboard/components/basemap.py`
- Create: `tests/test_basemap.py`

**Interfaces:**
- Consumes: `core.design` (`NAVY`, `LIGHT_BLUE`, `RED`, `RULE`, `MUTED`).
- Produces, used by every later task:
  - `leaflet_map(center: tuple[float, float], zoom: float, height: int = 560) -> folium.Map`
  - `render_map(m: folium.Map, key: str, height: int = 560, returned: Sequence[str] = ()) -> dict[str, object]`
  - `TILES: str`, `SELECTION_KEYS: tuple[str, ...]`

- [ ] **Step 1: Tell the peer session, then install**

The `.venv` is shared. Message the peer first, then:

```powershell
uv add folium streamlit-folium
uv sync --all-extras
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_basemap.py
"""basemap.py is the only place tiles, attribution and map colour are set.

The rerun assertions matter more than they look: st_folium returns 15 keys by default,
including bounds and zoom, which change on every pan -- and a changed return value
reruns the Streamlit script, which on these pages re-reads the lake."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "dashboard"))

from components import basemap  # noqa: E402
from core import design  # noqa: E402


def test_uses_the_pale_keyless_basemap() -> None:
    assert basemap.TILES == "CartoDB positron"


def test_map_renders_attribution_and_disables_scroll_zoom() -> None:
    m = basemap.leaflet_map(center=(50.0, 10.0), zoom=4)
    rendered = m.get_root().render()
    assert "OpenStreetMap" in rendered
    assert "CARTO" in rendered
    # Scroll-wheel zoom hijacks page scrolling inside a long Streamlit page.
    assert "scrollWheelZoom: false" in rendered


def test_selection_keys_exclude_everything_that_changes_on_pan() -> None:
    """bounds/zoom/center change on every pan; last_clicked fires on empty-map clicks."""
    assert basemap.SELECTION_KEYS == ("last_object_clicked_tooltip",)
    for key in ("bounds", "zoom", "center", "last_clicked"):
        assert key not in basemap.SELECTION_KEYS


def test_render_map_never_defaults_to_returning_everything() -> None:
    """returned_objects=None is the failure mode: it returns all 15 keys."""
    import inspect

    source = inspect.getsource(basemap.render_map)
    assert "returned_objects" in source
    assert "returned_objects=None" not in source


@pytest.mark.parametrize("colour", ["NAVY", "LIGHT_BLUE", "RED"])
def test_map_colours_come_from_the_design_module(colour: str) -> None:
    assert getattr(basemap, colour) is getattr(design, colour)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_basemap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'components.basemap'`

- [ ] **Step 4: Write the module**

```python
# apps/dashboard/components/basemap.py
"""The one Leaflet map constructor -- tiles, attribution, colour and interaction.

Replaces go.Scattermapbox (2026-09-06 restyle). Two decisions are load-bearing:

CartoDB Positron rather than OpenStreetMap. OSM's coloured raster competes with the
overlay; Positron is built to sit under data. Both are free and keyless.

Every render passes an explicit returned_objects allow-list. st_folium returns 15 keys
by default, including bounds and zoom -- which change on every pan, and every changed
return value reruns the Streamlit script, which on these pages re-reads the lake."""

from __future__ import annotations

from collections.abc import Sequence

import folium
from streamlit_folium import st_folium

from core.design import LIGHT_BLUE, MUTED, NAVY, RED, RULE

__all__ = ["LIGHT_BLUE", "NAVY", "RED", "SELECTION_KEYS", "TILES", "leaflet_map", "render_map"]

TILES = "CartoDB positron"

#: The only key any of these maps consumes. Anything else reruns the page for nothing.
SELECTION_KEYS: tuple[str, ...] = ("last_object_clicked_tooltip",)

_MUTED = MUTED
_RULE = RULE


def leaflet_map(
    center: tuple[float, float], zoom: float, height: int = 560
) -> folium.Map:
    return folium.Map(
        location=list(center),
        zoom_start=zoom,
        tiles=TILES,
        # Hijacks page scrolling inside a long Streamlit page; zoom via the control.
        scrollWheelZoom=False,
        zoom_control=True,
        control_scale=True,
        height=height,
    )


def render_map(
    m: folium.Map,
    key: str,
    height: int = 560,
    returned: Sequence[str] = (),
) -> dict[str, object]:
    """Render and return only `returned`. Default () returns nothing: no interaction
    reruns the page at all, which is right for every map that is display-only.

    `use_container_width` here is st_folium's OWN parameter -- not the deprecated
    st.plotly_chart/st.dataframe argument CLAUDE.md bans."""
    return st_folium(
        m,
        key=key,
        height=height,
        use_container_width=True,
        return_on_hover=False,
        returned_objects=list(returned),
    )
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_basemap.py -v`
Expected: 7 passed. If `scrollWheelZoom: false` is absent, print `m.get_root().render()`
and match the real serialisation rather than weakening the assertion — the behaviour is
the point.

- [ ] **Step 6: Commit**

```bash
./.venv/Scripts/python.exe -m ruff check apps/dashboard/components/basemap.py tests/test_basemap.py
./.venv/Scripts/python.exe -m mypy apps
git add apps/dashboard/components/basemap.py tests/test_basemap.py pyproject.toml uv.lock
git commit -m "feat(maps): shared Leaflet basemap on design tokens"
```

---

### Task 2: Boundary geometry — real polygons, not centroid dots

The maps plot centroid dots today (`components/geo_centroids.py` exists precisely
because there is no boundary geometry). This task supplies it.

**Files:**
- Create: `apps/dashboard/geo/build_geo.py`
- Create: `apps/dashboard/geo/us_states.geojson`, `apps/dashboard/geo/countries.geojson`
- Create: `apps/dashboard/geo/regions.py`
- Create: `tests/test_geo.py`

**Interfaces:**
- Produces:
  - `regions.PADD_BY_STATE: dict[str, str]` — USPS code to `"PADD1"`..`"PADD5"`
  - `regions.load_us_states() -> dict` and `regions.load_countries() -> dict` — parsed GeoJSON
  - `regions.ZONE_BY_COUNTRY: dict[str, str]` — ISO-2 to ENTSO-E bidding zone, for zones that ARE a country

**Source and licence.** Natural Earth (public domain), already this repo's geometry
source — `pipelines/weather/CLAUDE.md:143` records cartopy rendering coastlines from
Natural Earth shapefiles cached from `naturalearth.s3.amazonaws.com`. Cartopy is already
installed and bundles shapely 2.1.2 and pyproj, so simplification needs **no new
dependency** and no geopandas.

**Why per-state polygons rather than dissolved PADD outlines.** A PADD is defined as a
group of states, so colouring each state polygon by its PADD renders the same choropleth
without a dissolve step — and it keeps internal state borders, which are informative on
a stocks map. Draw internal borders as hairlines in `RULE`, PADD edges heavier.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo.py
"""Vendored boundary geometry. The files are committed rather than downloaded at
runtime: a page must not depend on a network fetch to draw a map, and the geometry is a
stable geographic fact, matching the geo_centroids.py / cities.csv precedent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "dashboard"))

from geo import regions  # noqa: E402

GEO_DIR = Path(__file__).parent.parent / "apps" / "dashboard" / "geo"


def test_every_lower_48_state_maps_to_a_padd() -> None:
    states = {f["properties"]["postal"] for f in regions.load_us_states()["features"]}
    unmapped = states - set(regions.PADD_BY_STATE)
    assert unmapped == set(), f"states with no PADD: {sorted(unmapped)}"


def test_padds_are_the_five_eia_districts() -> None:
    assert set(regions.PADD_BY_STATE.values()) == {
        "PADD1", "PADD2", "PADD3", "PADD4", "PADD5",
    }


def test_geometry_is_valid_geojson_and_small_enough_to_commit() -> None:
    for name in ("us_states.geojson", "countries.geojson"):
        path = GEO_DIR / name
        assert path.exists(), f"{name} not vendored"
        # Simplified geometry keeps the repo and the page payload sane.
        assert path.stat().st_size < 900_000, f"{name} is {path.stat().st_size} bytes"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        assert data["features"], f"{name} has no features"


def test_countries_carry_the_iso_code_the_lake_joins_on() -> None:
    props = regions.load_countries()["features"][0]["properties"]
    assert "iso_a2" in props
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_geo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'geo'`

- [ ] **Step 3: Write the build script**

`apps/dashboard/geo/build_geo.py` is run by hand, not at import: it reads Natural Earth
through cartopy's cached shapefile reader, simplifies with shapely, keeps only the
properties the app joins on (`postal`, `name` for states; `iso_a2`, `name` for
countries), and writes the two GeoJSON files. Use the 1:110m scale — 1:10m is far too
heavy for a browser payload. Simplify with `shapely.simplify(tolerance=0.05,
preserve_topology=True)` and drop coordinate precision to 4 decimals (~11 m), which is
well beyond what a continental map resolves.

Document at the top of the file: the Natural Earth version, the scale, the tolerance,
and that regenerating it is a deliberate act, not part of any pipeline run.

- [ ] **Step 4: Write `regions.py`**

`PADD_BY_STATE` is a literal dict of all 50 states plus DC to their PADD, taken from
EIA's own definitions. Write it out in full — it is a stable fact, and a hand-maintained
table here matches `geo_centroids.py`'s own reasoning. `load_us_states()` and
`load_countries()` read the vendored files with `@st.cache_data` so the parse happens
once per session, not once per rerun.

- [ ] **Step 5: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_geo.py -v`
Expected: 4 passed. If a state is unmapped the test names it — fix the table, never the test.

- [ ] **Step 6: Commit**

```bash
git add apps/dashboard/geo tests/test_geo.py
git commit -m "feat(geo): vendor simplified Natural Earth boundaries and the PADD state map"
```

**Known limitation, to record in the module docstring rather than discover later:**
several ENTSO-E bidding zones are NOT whole countries — Italy, Sweden (SE1-SE4), Norway
(NO1-NO5) and Denmark (DK1/DK2) are split sub-nationally, and DE_LU spans two. Those
zones stay on centroid markers until someone sources real zone geometry; `ZONE_BY_COUNTRY`
covers only the zones that genuinely are a country, and the price map must fall back to a
marker for the rest rather than shading a whole country wrongly.

---

### Task 3: Migrate `padd_map` — the pilot, and the go/no-go gate

**Files:**
- Modify: `apps/dashboard/components/padd_map.py`
- Modify: `tests/test_pages_browser.py`

- [ ] **Step 1: Rewrite the renderer**

Replace the `go.Figure` / `go.Scattermapbox` construction with `leaflet_map(...)` and a
real choropleth — this is the surface that stops being dots:

```python
states = regions.load_us_states()
folium.GeoJson(
    states,
    name="PADD districts",
    style_function=lambda feature: {
        "fillColor": _padd_fill(regions.PADD_BY_STATE[feature["properties"]["postal"]]),
        "color": RULE,          # hairline internal state borders
        "weight": 0.6,
        "fillOpacity": 0.75,
    },
    highlight_function=lambda _: {"weight": 2, "color": NAVY},
    tooltip=folium.GeoJsonTooltip(
        fields=["name"], aliases=[""], sticky=False
    ),
).add_to(m)
```

`_padd_fill` maps a PADD to a step on a **single-hue** sequential ramp derived from
`NAVY` — one hue, light to dark, never a rainbow, and never the categorical series
colours (a PADD's shade encodes a magnitude, not an identity).

Flows stay `folium.PolyLine`, keeping the exact lat/lon and `bearing_degrees` logic
already in the file. Terminals and entry points keep `folium.CircleMarker` — a point
facility genuinely is a point.

Render with `render_map(m, key="padd_flow_map")`, leaving `returned` at `()`: this
surface has no selection behaviour.

- [ ] **Step 2: Teach the browser test to see inside the iframe**

This is the step that stops a false pass — a folium map renders in an iframe, so the
existing top-level assertions cannot see it and would report success on a blank map.

```python
def test_leaflet_map_renders_inside_its_iframe(page: Page, streamlit_server: str) -> None:
    """A folium map lives in an iframe; asserting against the top-level document would
    pass on a blank map. Assert on the Leaflet DOM the map actually builds."""
    page.goto(f"{streamlit_server}/us_padd", wait_until="load", timeout=180_000)
    frame = page.frame_locator('iframe[title*="folium"], iframe[srcdoc*="leaflet"]').first
    frame.locator(".leaflet-container").wait_for(state="visible", timeout=60_000)
    assert frame.locator(".leaflet-marker-icon, .leaflet-interactive").count() > 0
```

- [ ] **Step 3: Run both test layers**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -q`
Run: `./.venv/Scripts/python.exe -m pytest -m browser -q`
Expected: both green, including the new iframe assertion.

- [ ] **Step 4: Measure the rerun cost — this is the gate**

Start the app, open `/us_padd`, and pan and zoom the map repeatedly while watching for
Streamlit's running indicator. **A pan must not rerun the page.** If it does,
`returned_objects` is not being honoured and the migration is not viable as designed.

**Go/no-go.** If the map is slow, reruns on pan, or renders wrong at either viewport,
STOP here and report. The spec's fallback is explicit: keep `padd_map` on Leaflet, leave
the other three on Plotly, and revisit. The surfaces are independent, so stopping is a
coherent outcome rather than a half-migration.

- [ ] **Step 5: Commit**

```bash
git add apps/dashboard/components/padd_map.py tests/test_pages_browser.py
git commit -m "feat(maps): move the PADD map to Leaflet, and assert through the iframe"
```

---

### Task 4: Migrate `entsog_map`

**Files:** `apps/dashboard/components/entsog_map.py`

- [ ] **Step 1: Rewrite with the same pattern as Task 3**

Corridors become `folium.PolyLine` with `folium.plugins.PolyLineTextPath` (or a terminal
`folium.RegularPolygonMarker`) for direction, coloured `NAVY` at capacity and
`LIGHT_BLUE` partial, keeping the existing `bearing_degrees` logic from
`components/geo_utils.py` unchanged. Tooltip per corridor: point name, flow, % capacity.
Render with `render_map(m, key="entsog_corridors")`.

- [ ] **Step 2: Verify and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -q && ./.venv/Scripts/python.exe -m pytest -m browser -q`
Open `/eu_gas_flows`, confirm direction markers read correctly and a pan does not rerun.

```bash
git add apps/dashboard/components/entsog_map.py
git commit -m "feat(maps): move the ENTSOG corridor map to Leaflet"
```

---

### Task 5: Migrate `power_maps` (two surfaces)

**Files:** `apps/dashboard/components/power_maps.py`

- [ ] **Step 1: `render_price_map()` — polygons where a zone is a country, markers where it isn't**

For every bidding zone in `regions.ZONE_BY_COUNTRY`, shade that country's polygon from
`regions.load_countries()` on a single-hue sequential ramp by price — one hue, light to
dark, never a rainbow, never the categorical series colours.

For the zones that are **not** whole countries — Italy, SE1-SE4, NO1-NO5, DK1/DK2, and
DE_LU which spans two — fall back to a `folium.CircleMarker` at the existing centroid,
coloured on the same ramp. **Do not shade a whole country for a sub-national zone**: it
would state something false about where that price applies. Add a one-line note under
the map naming which zones are shown as points and why.

Tooltip on both forms: zone, price, hour.

- [ ] **Step 2: `render_flow_map()`**

Cross-border flows follow Task 4's PolyLine pattern.

- [ ] **Step 3: Verify and commit**

```bash
git add apps/dashboard/components/power_maps.py
git commit -m "feat(maps): move the ENTSO-E price and flow maps to Leaflet"
```

---

### Task 6: Migrate `news_map` and retire the workaround

The payoff task: `news_map.py:8-21` documents that `st.plotly_chart(on_select=...)` is
unreliable for map traces, and the module carries a `go.Scattermap` migration purely to
work around it.

**Files:** `apps/dashboard/components/news_map.py`, `apps/dashboard/pages/09_events.py`

- [ ] **Step 1: Rewrite with real selection**

Event points become `folium.CircleMarker` with `tooltip` set to the event's stable id, so
the returned `last_object_clicked_tooltip` identifies it. Render with:

```python
state = render_map(m, key="news_map", returned=SELECTION_KEYS)
selected = state.get("last_object_clicked_tooltip")
```

Hold `selected` in `st.session_state` so the selection survives the rerun the click
causes, and draw the selection ring from that Python state rather than from Leaflet.
Provide a "Clear selection" control — without one a selection cannot be undone.

- [ ] **Step 2: Replace the docstring**

Delete the `on_select` explanation and the `go.Scattermap` rationale. Replace with two or
three lines recording that selection now comes from `st_folium`'s return value, and why
the module moved.

- [ ] **Step 3: Verify the selection actually works**

Run the app, open `/events`, click a point: the linked list below must filter to it, and
clearing must restore. Then confirm panning still does not rerun.

Run: `./.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -q && ./.venv/Scripts/python.exe -m pytest -m browser -q`

- [ ] **Step 4: Commit**

```bash
git add apps/dashboard/components/news_map.py apps/dashboard/pages/09_events.py
git commit -m "feat(maps): real click selection on the news map, retiring the on_select workaround"
```

---

### Task 7: Rules, cleanup, evidence

**Files:** `CLAUDE.md`, `CHANGELOG.md`

- [ ] **Step 1: Amend the map rule in `CLAUDE.md`**

The "Dashboard layout" section says maps use `go.Scattermapbox` with the free
`open-street-map` style and never `go.Scattergeo`. Rewrite the first half to describe
`basemap.leaflet_map` on CartoDB Positron; **keep** the `Scattergeo` prohibition and the
no-token requirement, both of which still hold. Add one line: every `st_folium` call
passes an explicit `returned_objects`, and why.

- [ ] **Step 2: Confirm no Plotly map traces remain**

Run: `grep -rn "Scattermapbox\|go.Scattermap\|open-street-map" apps/`
Expected: no matches outside comments describing the migration.

- [ ] **Step 3: Full gate**

Run: `./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy core pipelines infra apps && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m pytest -m browser -q`

- [ ] **Step 4: Screenshots and changelog**

Re-shoot the four map surfaces and compare against the before set. Add a `CHANGELOG.md`
entry in the established narrative style, recording the selection workaround this
retired and the rerun contract that keeps it fast.

```bash
# Stage by name -- a peer session writes to this repo.
git add CLAUDE.md CHANGELOG.md
git commit -m "docs(maps): describe the Leaflet map rule and record the migration"
```

## Definition of done

- [ ] `basemap.leaflet_map` is the only place tiles, attribution and map colour are set.
- [ ] All four surfaces render Leaflet maps reading `core/design.py`.
- [ ] `news_map` selection works through `st_folium`; the `on_select` workaround is gone.
- [ ] Panning or zooming any map does not rerun the page.
- [ ] The browser test asserts map content through the iframe.
- [ ] `make check` green; `pytest -m browser` green.
- [ ] `CLAUDE.md` map rule describes Leaflet; `Scattergeo` prohibition intact.
- [ ] Before and after screenshots of the four surfaces recorded.
