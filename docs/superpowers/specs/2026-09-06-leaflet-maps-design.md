# Design — Leaflet maps (folium / streamlit-folium)

**Date:** 2026-09-06
**Status:** approved design, not yet planned
**Branch:** `design/ui-restyle`
**Depends on:** `2026-09-06-ui-design-system-design.md` — ships after it, so the maps are
built against settled tokens rather than restyled twice.

## Why

The user asked for Leaflet. Leaflet is not a Claude Code plugin and not a Python library;
in Streamlit it is reached through `folium` (a Leaflet.js wrapper) plus
`streamlit-folium`. Beyond matching the request, there is a concrete existing problem it
solves: `apps/dashboard/components/news_map.py:8-21` documents that
`st.plotly_chart(on_select=...)` selection is unreliable for `Scattermapbox`, and that
the module carries a migration to `go.Scattermap` specifically to work around it.
`st_folium` returns click state as an ordinary return value, so the workaround retires.

## Goal

The five Plotly map surfaces become Leaflet maps that read the design tokens, with
click and hover behaviour that works rather than being worked around.

## Non-goals

- Not the cartopy anomaly maps on `08_weather` (Spec 08 Session B). Those are
  matplotlib raster fields, not point/vector overlays; Leaflet is the wrong tool and
  they stay as they are.
- No new data, no pipeline change. Maps read the same lake tables through the same
  helpers.
- No Mapbox account or token. Tiles stay free and keyless.

## Scope — the surfaces to migrate

| Component | Surface |
|---|---|
| `padd_map.py` | US PADD stocks / flows |
| `entsog_map.py` | ENTSOG directional corridors (Europe) |
| `power_maps.py` | `render_price_map()` and `render_flow_map()` |
| `news_map.py` | World news/events points, with click selection |

`geo_utils.py` (`bearing_degrees`) and `geo_centroids.py` (`centroid_for`) are geometry
helpers with no Plotly dependency and are reused unchanged.

## Architecture

### `apps/dashboard/components/basemap.py` — one shared constructor

A single `leaflet_map(...)` factory returning a configured `folium.Map`, so the four
components do not each re-specify tiles, attribution, zoom behaviour and colour. It owns:

- **Tiles.** CartoDB Positron rather than the current OpenStreetMap. OSM's coloured
  raster is visually loud under the white/hairline identity and competes with the data
  overlay; Positron is a pale basemap designed to sit under data. Both are free and
  keyless. Attribution is rendered — a licence requirement, not a style choice.
- **Colour.** Marker, line and choropleth colours come from `core/design.py`, the same
  module the charts read, so a map and a chart on one page cannot disagree.
- **Interaction defaults:** scroll-wheel zoom off by default (it hijacks page scrolling
  inside a long Streamlit page), fixed height, `zoom_control` on.

### Rendering and state

Components render through `st_folium(...)` with an explicit `key` and a `returned_objects`
allow-list. The allow-list matters: `st_folium` returns viewport state on every pan and
zoom by default, and each return triggers a Streamlit rerun, which on these pages means
re-reading the lake. Restricting returns to what a page actually consumes — the clicked
object for `news_map`, nothing for the others — keeps a pan from re-running a page.

`news_map` reads `last_object_clicked` (or the tooltip payload) in place of the
`on_select` event, and its long docstring about the Scattermapbox selection gap is
replaced with a short note recording why the migration happened.

### Dependencies

`folium` and `streamlit-folium` added to `pyproject.toml`, pinned in `uv.lock`. Both are
pure Python wrappers over vendored JS; neither needs a system library, unlike cartopy.

## Error handling and edge cases

- **Tiles unavailable** (offline, or the CDN blocked): the map renders its overlay on an
  empty ground rather than failing. Tests must not depend on tile pixels.
- **Empty geometry:** a source with no rows renders the `empty_state` component from the
  companion spec, not a blank world map.
- **Missing centroid:** `centroid_for` already returns `None` for an unknown geo; those
  rows are skipped and counted in the source note rather than silently dropped.
- **Iframe height:** `st_folium` renders in an iframe with a fixed pixel height, so it
  does not participate in Streamlit's normal column stretching. Height is set per
  surface and checked at the narrow viewport as well as the wide one.

## Testing

- `tests/test_pages_browser.py` asserts against rendered page content and counts console
  errors. A folium map lives **inside an iframe**, so assertions that look for map
  content in the top-level document will not see it and must switch to a
  `frame_locator`. This is the main test-side change and the main risk of a silent
  false-pass.
- The smoke test (`AppTest`) does not execute JS, so it proves only that the map is
  constructed without raising — same guarantee as today, no weaker.
- Manual check per surface: click behaviour on `news_map`, and confirming a pan does not
  trigger a lake re-read (visible as a rerun in the running app).
- Before and after screenshots of the four surfaces.

## `CLAUDE.md`

The "Dashboard layout" section currently states: maps use `go.Scattermapbox` with the
free `open-street-map` style, never `go.Scattergeo`. That rule is amended to describe
Leaflet via `basemap.leaflet_map`, keeping the `Scattergeo` prohibition and the
no-token requirement, both of which still hold.

## Risks

- **Rerun cost.** `st_folium` returning state on interaction is the known failure mode of
  this library; the `returned_objects` allow-list is the mitigation and must be in the
  first commit, not added later.
- **Loss of a single chart theme.** Plotly maps inherit the `kardamow` template; Leaflet
  maps will not. `basemap.py` reading `core/design.py` is what keeps them consistent, and
  it is the reason this spec ships after the token module exists.
- If either risk proves worse than expected on the first surface (`padd_map`), the
  fallback is to stop there and keep the remaining three on Plotly — the surfaces are
  independent, so a partial migration is coherent rather than broken.

## Definition of done

- [ ] `basemap.leaflet_map` is the only place tiles, attribution and map colour are set.
- [ ] All four surfaces render Leaflet maps reading `core/design.py` tokens.
- [ ] `news_map` click selection works through `st_folium` return state; the
      `on_select` workaround and its docstring are gone.
- [ ] Panning or zooming any map does not trigger a lake re-read.
- [ ] `tests/test_pages_browser.py` asserts map content through the iframe and passes.
- [ ] `make check` green; `pytest -m browser` green.
- [ ] `CLAUDE.md` map rule describes Leaflet.
- [ ] Before and after screenshots of the four surfaces recorded.
