# Spec 04 — European Power: Prices, Generation & Cross-Border Flows (ENTSO-E + EirGrid)

**Week 6 · Est. 10–14 h · Prereq: Spec 00.**

## Objective & alpha question
Day-ahead prices per bidding zone, generation mix, and cross-border physical flows show where
scarcity or renewables gluts price power — plus a live Ireland edge (home market) via EirGrid.

## Data sources
1. **ENTSO-E Transparency Platform** via `entsoe-py` (EnergieID, v0.8.x — actively maintained).
   Token: free, requested by email to transparency@entsoe.eu with "Restful API access" in the
   subject → `settings.entsoe_api_key`. Respect ~400 req/min (client sleeps built-in).
   Methods: `query_day_ahead_prices`, `query_crossborder_flows` (physical), `query_generation`
   (per PSR type), `query_load`, `query_wind_and_solar_forecast`, `query_installed_generation_capacity`.
   Zones to cover: DE_LU, FR, NL, BE, AT, ES, IT_NORD, PL, NO_2, SE_4, DK_1, IE_SEM, GB (as available).
2. **EirGrid Smart Grid Dashboard** — public undocumented JSON:
   `https://www.smartgriddashboard.com/DashboardService.svc/data?area={demandactual|generationactual|windactual|co2intensity|interconnection}&region={ROI|NI|ALL}&datefrom=DD-Mon-YYYY 00:00&dateto=...`
   Treat as fragile: cache aggressively, be gentle, wrap the response shape in one adapter function
   so a format change breaks exactly one file.

## Data model
- Prices/load/generation/forecasts → `ts_long` (`geo`=bidding zone, `freq`='H' or '15T').
- Cross-border → `flows(source='entsoe', from_node='DE_LU', to_node='FR', mode='power', unit='MW')`.
- EirGrid series → `ts_long` (`source='eirgrid'`, geo='IE'/'NI').

## Transformations
- Residual load = load − wind − solar. — Net position per zone = Σ exports − Σ imports.
- Price spreads between neighbouring zones; congestion flag = |spread| > threshold with interconnector at limit.
- Ireland: SNSP proxy = (wind + solar + HVDC imports) / demand.

## Visualisation spec (page `04_eu_power.py`)
1. **Price map**: Europe choropleth-style map of latest day-ahead price per zone (like ENTSO-E/EPEX map), diverging colour, price labels on zones.
2. **Cross-border arrow map**: arrows sized by latest hourly physical flow.
3. **Generation mix**: stacked area per selectable zone (renewables greens/blues, thermal greys/navy).
4. **Ireland panel**: demand vs wind (dual-axis), SNSP gauge, interconnector flows (EWIC/Celtic/Moyle).

## Sessions

### Session A (weekday, 1 h) — entsoe-py + prices
> Read NOTES.md, specs/04_entsoe-eu-power.md. Scaffold `pipelines/entsoe/` wrapping
> EntsoePandasClient. Pull 90 days of day-ahead prices for DE_LU, FR, NL, IE_SEM → ts_long.
> Cassette test (filter the token). Acceptance: yesterday's DE_LU price matches the TP UI.

### Session B (weekend, 3 h) — generation, load, flows + maps
> Pull generation mix, load, wind/solar forecast for the zone list; cross-border physical flows
> for all adjacent pairs among the covered zones → flows. Build page 04: price map, arrow map,
> generation-mix stack. Compute residual load and net position. Acceptance: page renders offline;
> one flow value cross-checked.

### Session C (weekend, 2–3 h) — EirGrid Ireland panel
> `pipelines/eirgrid/` with the DashboardService adapter (single response-parsing function),
> pulling ROI demand, wind, CO2 intensity, interconnection at 15-min resolution. Build the Ireland
> panel with SNSP. Acceptance: current ROI demand within tolerance of smartgriddashboard.com.

### Session D (weekday, 1 h) — daily entrypoint + polish
> `pull_daily.py` (prices after ~12:45 CET publication; actuals for prior day). Idempotency checks.

## Definition of Done
- Page 04: price map, arrow map, mix stack, Ireland panel. ≥10 zones priced, ≥8 borders flowing.
- EirGrid adapter isolated in one function. Cross-checks done. Tests green.

## Stretch
- Spark/dark spreads per zone using gas (TTF from Spec 07) and carbon (add EUA price when available).
- Day-ahead price forecast error tracking vs your own naive seasonal model.
