# Spec 02 — European Gas Storage & LNG Inventories (GIE AGSI+ / ALSI+)

**Week 3 · Est. 6–8 h · Prereq: Spec 00.**

## Objective & alpha question
EU storage fill % vs the 5-year corridor is the single most-watched TTF driver; ALSI+ LNG send-out
shows import substitution in near-real-time. Question answered daily: *is Europe filling/draining
faster than seasonal norms, and which countries are the swing?*

## Data source
GIE APIs — AGSI+ `https://agsi.gie.eu/api`, ALSI+ `https://alsi.gie.eu/api`. One free key with
access set to "Both" (`settings.gie_api_key`, sent as `x-key` header). IP rate-limited (~60 s
cool-off if flooded) — sequential requests with backoff, paginate historical pulls. Daily data
lands ~19:30 CET. Use the `gie-py` client (`GiePandasClient`) OR direct REST — decide in-session
based on how well `gie-py` handles pagination; prefer direct REST if in doubt.

Pulls: EU + per-country daily history since 2018 (AGSI: `gasInStorage`, `full` %, `injection`,
`withdrawal`, `workingGasVolume`; ALSI: `lngInventory`, `sendOut`, `dtmi`).

## Data model
`ts_long` with ids like `agsi.EU.full_pct`, `agsi.DE.net_injection`, `alsi.EU.sendout`;
`geo` = ISO country or `EU`; `freq='D'`.

## Transformations
- Fill-% seasonal corridor (5-yr min/max/median, excl. 2020 via `core.seasonal`).
- Net flow = injection − withdrawal; days-to-full/empty at trailing 7-day rate.
- ALSI send-out 7-day avg; send-out as % of nameplate (dtmi).
- Country deviation table: current fill vs seasonal median, ranked.

## Visualisation spec (page `02_gas_storage.py`)
1. EU fill-% seasonal "worm" (headline chart, big annotation: Latest / vs median / days-to-full).
2. Small-multiples grid: DE, NL, FR, IT, AT, PL fill-% worms.
3. Dual-axis: EU net injection (navy) vs ALSI send-out (light blue).
4. Ranked country deviation bar chart (red below median, navy above).

## Claude Code sessions

### Session A (weekday, 1 h) — client + one country
> Read CLAUDE.md, specs/02_gie-gas-storage.md. Scaffold `pipelines/gie/` (client.py, CLAUDE.md,
> cassette test). Implement authenticated GET with `x-key` header, retry/backoff honouring the
> 60 s cool-off, and date-window pagination. Pull Germany AGSI daily history 2018→today → ts_long.
> Cassette must filter the x-key header. Acceptance: DE fill % matches agsi.gie.eu for yesterday.

### Session B (weekend, 3 h) — full EU + page
> Extend to EU aggregate + all member countries + ALSI EU/country send-out. Build page 02 with the
> four visuals in the spec. Wire `days_to_full()` into the headline annotation. Acceptance: page
> renders offline; EU fill % cross-checked against the AGSI website; tests green.

### Session C (weekday, 1 h) — hardening
> Handle provisional-vs-revised data (re-pull trailing 5 days on every run, de-dup by revision_date).
> Add `pull_daily.py` entrypoint for orchestration (Spec 13). Update pipelines/gie/CLAUDE.md.

## Definition of Done
- [x] Page 02 live with 4 visuals; EU + ≥6 countries; daily re-pull idempotent with 5-day revision window.
- [x] One cross-checked value vs the AGSI+ site. Tests + CI green.

Done as of 2026-08-29 (PR #5, Sessions A-C). EU + 19 countries pulled (AGSI) / EU + 13
LNG-terminal countries (ALSI), well past the ≥6 minimum. Cross-verification done against
GIE's own API directly (independent live calls, exact-value match), same approach as Specs
00-01, for the same reason: comparing exact numbers is a stronger check than eyeballing the
agsi.gie.eu/alsi.gie.eu dashboard UI. `pull_daily.py`'s idempotency and revision-refresh
behaviour verified directly (re-ran it twice; zero duplicate rows; confirmed revision_date
actually refreshes inside the trailing 5-day window and stays untouched just outside it).

## Stretch
- Join TTF front-month (from Spec 07's IB pipeline once built) and plot storage-deviation vs price.
- Simple storage-trajectory projection to 1 Nov at current 14-day net-injection pace.
