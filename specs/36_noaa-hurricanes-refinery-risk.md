# Spec 36 — NOAA Hurricanes & Gulf Coast Refinery Capacity at Risk

**Est. 5–6 h (three sessions) · Prereq: Spec 01 (EIA client), Spec 20 (cracks). Optional:
Spec 35 for RB option pricing. New sources: NOAA NHC, EIA refinery capacity by plant.
Independent of Spec 34 for Sessions A–B.**

## Objective & alpha question

PADD 3 holds roughly half of US refining capacity, and it sits in the Atlantic hurricane belt.
The lake already has Gulf Coast product spot prices and cracks; it has no storms and no
refinery locations.

Question: *when a storm cone overlaps Gulf Coast refining, how much capacity is at risk, and
does the gasoline crack and its option skew price that exposure before landfall — or after?*
This is a reinsurance-style exposure calculation applied to a commodity spread: hazard × exposure
→ expected capacity loss → a crack and vol view.

## Sources — what Session A must verify live

| Source | Use | Verify |
|---|---|---|
| NHC active storms feed (`nhc.noaa.gov`, current-storms JSON) | live advisories, position, intensity | exact URL and fields; behaviour with no active storm |
| NHC forecast cone / track GIS | cone polygons per advisory | format (shapefile/KMZ), retention of past advisories |
| HURDAT2 Atlantic best-track | history back to 1851 for base rates | current file name (it is versioned by release date) |
| EIA refinery capacity by plant (annual refinery capacity report) | operable capacity per refinery | file format and table; **plant coordinates** — if the capacity file lacks them, find EIA's own refinery location layer and record which; never geocode by name guesswork |

Record every URL, format and quirk in `pipelines/noaa/CLAUDE.md`. NOAA data is public domain;
EIA terms as per existing pipelines.

## Data model

- Storm positions and intensity → `ts_long`: `noaa.storm.<atcf_id>.lat` / `.lon` / `.vmax_kt` /
  `.mslp_mb`, `freq="6H"` best-track, advisory cadence for live.
- Refinery capacity → a small reference table `ref_refineries` (`eia_plant_id, name, state, padd,
  lat, lon, operable_bpd, as_of_year`) — reference data, not a time series. Add to
  `core/schemas.py`.
- Derived → `derived.hurricane.padd3.capacity_in_cone_bpd` and `.share_pct`, per advisory.
- Cones stored as GeoJSON files under `data/raw/noaa/cones/`, keyed by storm and advisory.

## Analytics — `core/hurricane.py` (pure, no DuckDB)

```python
def capacity_in_cone(cone: Polygon, refineries: pd.DataFrame) -> float          # bpd
def landfall_window(track: pd.DataFrame, coast: LineString) -> tuple[ts, ts] | None
def historical_exposure(hurdat: pd.DataFrame, refineries: pd.DataFrame,
                        radius_km: float = 150) -> pd.DataFrame                 # per storm
def event_study(cracks: pd.Series, events: pd.DataFrame,
                window=(-10, 20)) -> pd.DataFrame                               # crack path around landfall
```

Use `shapely`. Note honestly that today's refinery set is applied to past storms — capacity has
changed over time, so historical exposure is a proxy and is labelled as one.

## Sessions

### Session A — NHC + HURDAT2 pipeline (~2 h)

> Read `CLAUDE.md`, `specs/36_noaa-hurricanes-refinery-risk.md`. Verify the NHC feed, cone GIS
> and HURDAT2 file live. `/new-pipeline noaa`: client, parser for HURDAT2's fixed-width format,
> live-advisory puller that exits cleanly (zero rows, exit 0) when no storm is active, cone
> download. Cassette tests including the no-storm case. Register live pull at the advisory cadence
> in season only (June–November), from config.

### Session B — refinery reference + exposure maths (~2 h)

> Verify the EIA refinery capacity source and coordinates live. Load `ref_refineries`.
> Build `core/hurricane.py` with tests on synthetic polygons (a cone covering exactly two
> known plants returns their summed capacity). Compute historical exposure for every HURDAT2
> storm since 2000 that came within the radius of a PADD 3 plant.

### Session C — event study and page (~2 h)

> Event study: RB crack (Spec 20) and, if Spec 35 is live, RB ATM vol, from 10 days before to
> 20 days after landfall, split by capacity-at-risk bucket. Page card: live cone map over
> refinery bubbles sized by capacity (MapLibre/Plotly, house style), capacity-in-cone headline,
> and the event-study fan. State the sample size on the card — a handful of large storms is not a
> distribution, and the caption says so.

## Acceptance criteria

- [ ] All four sources verified live; URLs and quirks recorded; no geocoding by guesswork.
- [ ] No-active-storm run exits 0 with zero rows (tested).
- [ ] `capacity_in_cone` tested on synthetic geometry with an exact expected figure.
- [ ] Historical exposure labelled as a proxy (today's refinery set on past storms).
- [ ] Event-study card shows its sample size.
- [ ] Session ends green: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines infra`.
