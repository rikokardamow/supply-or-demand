# Spec 12 — Flight Traffic & Jet-Fuel Demand Proxy (OpenSky)

**Week 15 · Est. 6–8 h · Prereq: Spec 00.**

## Objective & alpha question
Regional flight counts as a jet-fuel-demand proxy; traffic recovery/decline front-runs kerosene
demand shifts. Basic FR24-style live map as a visual bonus.

## Data source — OpenSky Network (breaking auth change)
**Since 18 Mar 2026 basic auth is retired: OAuth2 client-credentials only.** Create an API client
on the OpenSky account page → `settings.opensky_client_id/_secret`; POST to the
`auth.opensky-network.org` token endpoint; tokens expire ~30 min → auto-refresh. Registered users:
**4,000 API credits/day** (8,000 if you feed an ADS-B receiver ≥30% uptime; anonymous ~400 and
current-state-only). `/states/all` with a bounding box costs fewer credits than global — always box.
Endpoints: `GET /api/states/all?lamin&lomin&lamax&lomax` (state vectors), `/api/flights/arrival|departure` (by airport, historic).
Free supplements if credits bind: adsb.lol / adsb.fi / airplanes.live (check each ToS in-session).

## Credit budget (design constraint)
Snapshots per region per hour, not continuous polling: 6 regions × 24/day = 144 calls ≈ well
inside 4,000 credits. Regions: Europe, N. America, Gulf/ME, SE Asia, plus Ireland close-up and
one chokepoint-adjacent box (Red Sea overflight, ties to Spec 11 narrative).

## Data model
- Hourly counts → `ts_long` (`flights.count.europe`, `freq='H'`).
- Latest raw snapshot per region → `data/lake/flights/latest/{region}.parquet` for the map (not history — storage discipline).

## Transformations
- Airborne count per region per hour → daily mean; 7-day avg; YoY; indexed jet-fuel proxy (2024=100).
- Optional: split by altitude band (>18,000 ft ≈ en-route commercial).

## Visualisation spec (page `11_flights.py`)
1. Live-ish map: latest snapshot dots (Plotly scattergeo/Mapbox), region selector, timestamp badge.
2. Regional flight-count time series (7-day avg, navy) small multiples with YoY annotations.
3. Dual-axis: Europe counts (navy) vs jet crack/HO proxy from Spec 07 (light blue) when available.

## Claude Code sessions

### Session A (weekday, 1 h) — OAuth2 + first snapshot
> Read CLAUDE.md, specs/12_flights.md. Scaffold `pipelines/flights/`: token manager (fetch,
> cache to memory, refresh before expiry, never log the token), `/states/all` bounding-box client,
> region definitions. One Europe snapshot → counts in ts_long + latest parquet. Cassette test with
> token filtered. Acceptance: count is plausible (thousands over Europe daytime).

### Session B (weekend, 3 h) — regions, history, page
> All 6 regions; hourly entrypoint with credit-budget guard (hard stop if projected daily calls
> > 3,500); page with map + small multiples. Backfill note: OpenSky history is limited on free
> tier — start accumulating now, document the series start date honestly on the page.

## Definition of Done
- 6 regional hourly series accumulating; live map with timestamp; credit guard tested.
- OAuth2 refresh proven across a >30 min run. Tests green.

## Stretch
- Airport-level departures for hub set (LHR, AMS, FRA, DXB, ATL) → weekly index.
- Cargo-heavy region split via ICAO prefix heuristics.
