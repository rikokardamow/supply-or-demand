# Spec 11 — Vessel Traffic, Chokepoints & Floating Storage (AIS via aisstream.io)

**Weeks 16–18 · Est. 20–28 h · The hardest module — do last. Prereq: Spec 00; Spec 06 (oil-on-water context).**

## Objective & alpha question — and an honesty clause
Chokepoint transit counts (Hormuz, Suez, Bab el-Mandeb, Malacca, Bosphorus, Panama), a
floating-storage proxy, and dark-fleet gap flags — reproducing the Exhibit-1 oil-on-water vs
floating-storage chart as a *proxy*, not a Kpler replica. **Honesty clause: aisstream.io is a
terrestrial network — coastal/chokepoint coverage is good, open ocean is patchy. All derived
series are labelled "AIS-derived proxy" on-page. Do not pay for commercial AIS speculatively;
Datalastic's trial is the only sanctioned experiment, and only after chokepoint proxies prove
useful in your actual research.**

## Data source
**aisstream.io** — free, global websocket: `wss://stream.aisstream.io/v0/stream`. Auth: API key in
the subscription message (`settings.aisstream_key`). Subscription JSON:
`{"APIKey": "...", "BoundingBoxes": [[[lat1,lon1],[lat2,lon2]], ...], "FilterMessageTypes": ["PositionReport","ShipStaticData"]}`.
Behavioural constraints: server drops you if your read queue backs up → consume fast, buffer to
disk, reconnect with exponential backoff + jitter; expect disconnects as normal.
Vessel registry enrichment: Equasis (free, manual lookups only — no bulk scraping).

## Geofences (`pipelines/ais/geofences.py` — hand-curated polygons)
Chokepoints (tight boxes + inner "gate" line for crossing detection): Hormuz, Suez (canal + Gulf
of Suez), Bab el-Mandeb, Malacca/Singapore, Bosphorus, Panama (both approaches), Danish Straits,
Cape of Good Hope (wide box, count only). Anchorage zones for floating storage: Singapore OPL,
Fujairah, Malta/Kalamata, Rotterdam, Ceuta/Gibraltar, off-Malaysia (Linggi), Yosu/Ningbo approaches.
Store as WKT in a versioned CSV; use `shapely` (`uv add shapely`) for point-in-polygon.

## Architecture (long-running process — NOT GitHub Actions)
```
ingester (asyncio websocket) ── append JSONL.gz → data/raw/ais/YYYY/MM/DD/HH.jsonl.gz
compactor (hourly)           ── raw → Parquet vessel_positions (dedup, downsample to 1 pos/vessel/5min)
derivers (hourly/daily)      ── transits, floating storage, gaps → ts_long + tables
dashboard page               ── reads lake only
```
Runs on your laptop initially (systemd/launchd or a tmux session); a €5 VPS is the stretch home.
Storage discipline: raw retained 30 days then deleted; Parquet keeps the 5-min downsample only.

## Data model
`vessel_positions(mmsi, ts, lat, lon, sog, cog, nav_status, ship_type, draught)`;
`vessel_static(mmsi, imo, name, ship_type, dims)`; derived: `chokepoint_transits(chokepoint, ts, mmsi, direction, ship_class)`;
`ts_long` series: `ais.transits.hormuz.tanker.d`, `ais.floating_storage.mbbl_proxy`, `ais.oow.mbbl_proxy`, `ais.dark_gaps.count`.

## Transformations
- **Ship classes:** AIS type 80–89 = tanker; class by size (LR2/VLCC via dims/draught heuristics);
  LNG carriers = type 84 cross-checked against dims (~290 m) — document the heuristic, accept noise.
- **Transit detection:** segment-crossing of the gate line between consecutive positions of the
  same MMSI, direction from crossing sign; dedupe within 6 h per vessel.
- **Floating storage proxy:** laden (draught ≥ 0.8 × max observed draught for that MMSI) tanker,
  SOG < 0.5 kn for > 7 days within an anchorage polygon → sum estimated cargo
  (DWT-class barrels: VLCC ≈ 2.0 Mbbl, Suezmax ≈ 1.0, Aframax ≈ 0.7 — crude proxy, label as such).
- **Oil-on-water proxy:** Σ estimated cargo of laden tankers underway inside monitored boxes —
  *coverage-limited; chart alongside OPEC MOMR oil-on-water (Spec 06) as the authoritative series.*
- **Dark-gap flag:** vessel seen entering a monitored region, no position for > 12 h, reappears
  > 50 nm from dead-reckoned track (sog×cog projection) → flag. Count per week per region.

## Visualisation spec (page `12_vessels.py`)
1. Map: latest positions in monitored boxes, coloured by ship class; chokepoint polygons drawn; dark-gap flags as red markers.
2. Chokepoint transit counts: 7-day avg small multiples (navy) vs prior year (grey).
3. **Exhibit-1 replica:** MOMR oil-on-water (navy area, left axis) vs AIS floating-storage proxy (light-blue line, right axis) — clearly labelled proxy.
4. Dark-gap weekly counts by region (red bars).

## Sessions

### Session A (weekend, 3 h) — ingester
> Read NOTES.md, specs/11_ais-vessels.md. Build `pipelines/ais/ingester.py`: asyncio websocket
> client subscribing to the chokepoint + anchorage boxes with PositionReport/ShipStaticData
> filters; fast reader → bounded queue → gzip JSONL writer (hour-partitioned); reconnect with
> exponential backoff/jitter; heartbeat log line per minute (msgs/sec, queue depth); clean
> shutdown. No parsing beyond envelope. Acceptance: 30-minute run captures messages from ≥3
> chokepoints without disconnect-loop.

### Session B (weekday, 1 h) — run + observe (you)
> Leave the ingester running for 24–48 h. In-session: write `stats.py` summarising captured
> volume by box/hour to validate coverage before building on it. Descope any box with
> negligible coverage now.

### Session C (weekend, 3 h) — compactor + schema
> `compactor.py`: raw JSONL → vessel_positions Parquet (dedup, 5-min downsample, static-data
> table upsert); geofences.py with shapely + point-in-polygon tests (hand-placed test points);
> 30-day raw retention job. Acceptance: a day of raw compacts to Parquet with plausible vessel
> counts; unit tests green.

### Session D (weekend, 3 h) — transits + floating storage
> `derive_transits.py` (gate-crossing + 6 h dedupe) and `derive_storage.py` (laden-stationary
> logic + DWT-class cargo table) → ts_long. Unit tests with synthetic tracks (a vessel crossing
> Hormuz; a vessel parked 8 days at Fujairah laden vs ballast). Acceptance: synthetic cases
> produce exactly the expected transits/storage rows.

### Session E (weekend, 3 h) — dark gaps + page
> `derive_gaps.py` (dead-reckoning flag) with synthetic tests; build page 12 with all four
> visuals including the Exhibit-1 replica joining Spec 06's MOMR series. Hourly/daily deriver
> entrypoints documented for the local scheduler.

### Session F (weekday, 1 h) — hardening
> Ingester as a supervised service (restart-on-crash script), disk-usage guard, "data as of"
> badge on the page, and a coverage-honesty note rendered under the map.

## Definition of Done
- Ingester survives 48 h unattended; ≥5 chokepoints with usable transit series; floating-storage
  and dark-gap series computing; Exhibit-1 replica live with proxy labelling; synthetic-track tests green.

## Stretch
- Port-call detection (SOG<1 kn inside port polygon >4 h) for a 10-port set.
- Equasis-assisted ownership notes for repeat dark-gap MMSIs (manual, documented).
- Datalastic 14-day trial evaluation memo — only if the free proxies have already changed a research call.
