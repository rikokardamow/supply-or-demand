# pipelines/ais — notes

Spec 11, Sessions A and C (partial). The ingester captures raw AIS; the compactor turns
it into the latest position per vessel and publishes to `serving.vessel_latest`, which the
web map reads. The full `vessel_positions` history table, transit detection and the
floating-storage proxy are still unbuilt.

## Two honesty clauses that travel with every number derived from this

1. **aisstream.io is a terrestrial receiver network.** Coastal and chokepoint coverage is
   good; open ocean is patchy. An empty stretch of sea means no receiver, not no ships.
   Spec 11 states this as a binding clause: everything derived is a proxy and is labelled
   as one.
2. **Ship class is as reported, never verified.** The AIS type code is hand-entered by the
   crew and is frequently wrong or absent. `classify()` maps 80–89 to tanker, 84 to LNG,
   70–79 to cargo, and everything else — including a missing code — to `other`. A vessel
   reported as a tanker may not be one, and `other` conflates "something else" with
   "didn't say".

## The queue drops rather than blocks — deliberately

Spec 11 warns that aisstream disconnects a client whose read queue backs up. So the reader
never awaits the disk: it pushes into a bounded `asyncio.Queue` and, when that is full,
**discards the message and counts it**. Blocking would stall the socket and cost the
connection, and a dropped connection loses everything until reconnect; dropping loses a
handful of positions. Both lose data — only one loss is bounded. The count appears on
every heartbeat, so it is never silent.

Reconnects are normal, not exceptional. Backoff is exponential with **full jitter**: a
bare exponential has every client in a region retrying in lockstep after a server blip and
reproducing the overload.

## Live verification (2026-09-09)

A two-minute run captured **1,154 messages (9.6/s), 0 dropped, 0 reconnects** — 978
`PositionReport`, 175 `ShipStaticData`, **781 distinct vessels**. Coverage by region:

| Region | Messages |
|---|---|
| Rotterdam | 576 |
| Danish Straits | 323 |
| Gibraltar | 80 |
| Cape of Good Hope | 73 |
| Malacca | 51 |
| Suez | 40 |
| Bosphorus | 10 |

Seven regions in two minutes, comfortably past Spec 11's Session A acceptance of three.
Hormuz, Bab el-Mandeb, Panama and the anchorages saw nothing in that window — expected
for a two-minute sample, and the reason Session B is "leave it running for 24–48 h and
descope any box with negligible coverage" rather than a guess.

The compactor then produced **714 vessels**, all inside a monitored region, published to
`serving.vessel_latest` as real PostGIS geography spanning −34.7° to 56.3° latitude.

## Gotchas confirmed live

- **`MetaData.time_utc` is not ISO.** aisstream stamps e.g.
  `2026-09-09 14:12:03.123456789 +0000 UTC` — a Go time format, with nanoseconds Python's
  `fromisoformat` rejects. `_parse_ts` strips the suffix and sub-second part.
- **EWKT is longitude-first.** `POINT(lon lat)`, the reverse of AIS's own lat-first
  convention. Getting it the wrong way round puts every ship in the Gulf of Guinea, which
  is plausible enough on a map to miss.
- **Fujairah is outside the Hormuz box, correctly.** It sits on the Gulf of Oman, south of
  the strait — which is exactly why it matters as an anchorage. A box that swallowed it
  would count stationary storage as strait traffic. `tests/test_ais_geofences.py` asserts
  this so a future widening of the Hormuz box has to confront it.
- **Boxes are hand-curated rectangles, not hydrographic boundaries.** Deliberately wider
  than the waterway so a transit is seen on both approaches. Session D's gate lines are
  what will make transit detection precise.

## Running it

```powershell
.venv\Scripts\python.exe -m pipelines.ais.ingester --minutes 30   # bounded capture
.venv\Scripts\python.exe -m pipelines.ais.ingester                # until interrupted
.venv\Scripts\python.exe -m pipelines.ais.compactor               # raw -> serving
```

Not in `infra/run_scheduled.py`: the ingester is a long-running process, which is a
different shape from the cadence groups there. Spec 11 suggests a tmux session or a small
VPS. Raw files are hour-partitioned gzip JSONL under `data/raw/ais/YYYY/MM/DD/HH.jsonl.gz`;
Spec 11's 30-day retention job is not built yet, so they accumulate.

**Storage note**: vessel positions are the workload that will push Supabase past its 500 MB
free tier. The database sat at 423 MB before this landed. Continuous capture needs either
the Pro plan or a retention policy on `serving.vessel_latest` — it is one row per vessel,
so it stays small, but a future `vessel_positions` history table would not.
