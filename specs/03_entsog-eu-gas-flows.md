# Spec 03 — European Natural Gas Pipeline Flows (ENTSOG)

**Weeks 4–5 · Est. 12–16 h (point-mapping is the time sink) · Prereq: Spec 00; Spec 02 helpful.**

## Objective & alpha question
Directional pipeline flows (Norway→Europe, TAP, TurkStream, LNG entry points, interconnectors)
reveal supply reroutes and demand shifts days before monthly statistics. Also: physical flow vs
nomination gap = under-delivery signal.

## Data source
ENTSOG Transparency Platform — public, **no key**. REST:
`https://transparency.entsog.eu/api/v1/operationaldata` (append `.json`/`.csv`), params:
`indicator=Physical Flow` (also `Nomination`, `Renomination`, `Allocation`, `GCV`),
`pointDirection` / `pointKey`, `operatorKey`, `directionKey=entry|exit`, `from`, `to`,
`periodType=day`, `limit`. Directory: `/api/v1/operatorpointdirections.json` (all points, operators,
directions — cache this locally as Parquet, refresh monthly). The `entsog-py` client exists but is
patchily maintained — **call REST directly** with requests + pagination + backoff. Values arrive in
kWh/d; convert to GWh/d (and mcm/d at ~10.55 kWh/m³ GCV where useful). Data revised for ~15 gas-days.

## Corridor mapping (the real work)
Create `pipelines/entsog/corridors.py`: a hand-curated dict mapping corridor name → list of
`pointKey`+direction, starting with:
- `NO_EXPORTS`: Norwegian landing points (Emden EPT/NPT, Dornum, Zeebrugge ZPT, Dunkerque, Easington, St Fergus).
- `TAP`: Melendugno entry. — `TURKSTREAM_EU`: Strandzha 2/Malkoclar entry.
- `RU_UA_TRANSIT`: Sudzha/Uzhgorod points (may be zero/dormant — keep for history).
- `LNG_ENTRY`: per-country LNG terminal entry points (Gate, Zeebrugge LNG, Montoir, Fos, Barcelona…).
- Key interconnectors: DE↔FR, DE↔NL, DE↔PL, DE↔CZ/AT, ES↔FR (VIP Pirineos), UK↔BE/NL (IUK/BBL), IE entry (Moffat).
Populate keys from the cached directory in-session; validate each against the TP map UI. Document
every chosen pointKey in pipelines/entsog/CLAUDE.md.

## Data model
`flows(source='entsog', from_node, to_node, value(GWh/d), ts, mode='pipeline')` at point level,
plus a corridor-aggregated materialised view in DuckDB. Nominations stored alongside with
`mode='nomination'` for the gap calculation.

## Transformations
- Point → corridor aggregation; net flow per border (entry − exit).
- Physical − Nomination gap per corridor.
- 7/30-day rolling averages; YoY; corridor share of total EU supply.

## Visualisation spec (page `03_eu_gas_flows.py`)
1. **Sankey** (Plotly): sources (Norway, LNG, Algeria, TurkStream, TAP, storage net-withdrawal from Spec 02) → hubs → demand regions, latest 7-day avg.
2. **Corridor map**: `scattergeo` Europe with directional arrows sized by flow (or `pydeck` ArcLayer if it stays inside one session).
3. **Corridor time series**: small multiples, navy current vs grey prior-year.
4. **Physical-vs-nomination gap** chart for a selectable corridor.

## Claude Code sessions

### Session A (weekend, 3 h) — client + directory + corridors
> Read CLAUDE.md, specs/03_entsog-eu-gas-flows.md. Scaffold `pipelines/entsog/`: REST client
> (pagination, backoff, kWh→GWh conversion), cached operator-point directory, and `corridors.py`
> populated with real pointKeys for NO_EXPORTS, TAP, TURKSTREAM_EU and 3 interconnectors —
> validate each key exists in the directory and fail loudly otherwise. Cassette tests.
> Acceptance: yesterday's Norwegian exports total within a few % of the TP website figure.

### Session B (weekend, 3 h) — full pulls + Sankey
> Pull 2 years of daily physical flows for all mapped corridors → flows; nominations for the same
> points. Corridor aggregation view in DuckDB. Build the Sankey and corridor small-multiples on
> page 03. Acceptance: Sankey totals reconcile with corridor time-series totals.

### Session C (weekday, 1 h) — map
> Add the directional corridor map (scattergeo arrows sized by latest 7-day avg).

### Session D (weekday, 1 h) — gap + revisions
> Physical-vs-nomination gap chart; re-pull trailing 15 gas-days on every run (revision window);
> `pull_daily.py` entrypoint. Update CLAUDE.md with the final corridor→pointKey table.

## Definition of Done
- ≥8 corridors mapped, validated, documented. Sankey + map + small multiples + gap chart live.
- Norwegian export figure cross-checked. 15-day revision window implemented. Tests green.

## Stretch
- EU supply-demand balance closure: NO + LNG + other entry − exports ± storage (Spec 02) ≈ implied demand.
- Animated month-by-month arc map.
