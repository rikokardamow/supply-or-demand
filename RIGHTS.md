# RIGHTS.md

Every source this repo pulls, its terms as read, and the class that decides what the
serving layer may carry. Written from `core/rights.py` by `uv run python -m core.rights`;
edit that module, not this file (`tests/test_rights.py` checks they agree).

Classes (PROJECT-STARTER section 6): **a** may publish derived numbers, no attribution
burden. **b** the same, with attribution. **c** research or non-commercial only; may be
shown with the licence named and no ads. **d** no, or terms not read; private only.
`core/publish.py` drops class d rows before any SQL runs, and refuses a source that is
not in this table.

A class above d needs its terms read at source. "Read on" and "read by" say when and by
whom; the terms pages were fetched with a plain request and read in full. A page that
refused the request, or that held no re-use statement, leaves the source at d, "terms not
read". The six sources parked as I-06 are the one exception: they are held at class a,
the reading the README gave them, with no read date, until the owner decides. The owner's
register (`~/Projects/_runs/desk-core/RIGHTS.md`) classes all six d. Marking one d in
`core/rights.py` takes it off the serving layer at the next publish.


| source | name | what is used | terms as read here | class | owner register | public surfaces reached | credit line | terms page | read on | read by |
|---|---|---|---|---|---|---|---|---|---|---|
| `adanos` | Adanos sentiment API | daily buzz and sentiment scores by ticker and platform | terms not read | d | same | serving API (series_long) |  |  |  | not read |
| `ais` | aisstream.io | live AIS positions, compacted to the latest per vessel | terms not read | d | same | serving API (vessel_latest) |  |  |  | not read |
| `baker_hughes` | Baker Hughes rig count | North America rig counts | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | serving API (series_long) |  |  |  | not read |
| `cftc` | CFTC Commitments of Traders | disaggregated futures-only positions | CFTC web policy, Copyright: government information on the CFTC website is in the public domain; appropriate acknowledgement requested | b | same | README chart, serving API (series_long) | Source: CFTC Commitments of Traders | https://www.cftc.gov/WebPolicy/index.htm | 2026-11-21 | improve run-01 |
| `coal` | U.S. EIA coal, consumption and quality | power-sector coal receipts, stocks, price and heat content | EIA Copyrights and Reuse: U.S. government publications are in the public domain; an acknowledgment with the publication date is requested | b | same | serving API (series_long) | Source: U.S. Energy Information Administration | https://www.eia.gov/about/copyrights_reuse.php | 2026-11-21 | improve run-01 |
| `derived` | Series computed in this repo | cracks, spreads, positions, moving averages, Cushing utilisation, z-scores | inherits the worst class among its inputs; see the derived table below | inherit | same | web, serving API (series_long) |  |  |  | not read |
| `ecmwf` | ECMWF open data | IFS forecast runs for the weather anomaly maps | ECMWF open data page: use is governed by CC-BY-4.0 and the ECMWF Terms of Use; the data may be redistributed and used commercially, subject to attribution | b | same | weather maps | Contains modified ECMWF open data (CC BY 4.0) | https://www.ecmwf.int/en/forecasts/datasets/open-data | 2026-11-21 | improve run-01 |
| `eia` | U.S. Energy Information Administration, open data API v2 | WPSR, gas storage, EIA-930, prices, NYMEX ranks 1 to 4 to 2024-04-05 | EIA Copyrights and Reuse: U.S. government publications are in the public domain; an acknowledgment with the publication date is requested | b | same | README charts, web, serving API (series_long, seasonal, flows, wpsr_lines, spreads) | Source: U.S. Energy Information Administration | https://www.eia.gov/about/copyrights_reuse.php | 2026-11-21 | improve run-01 |
| `eirgrid` | EirGrid Smart Grid Dashboard | Irish and all-island demand, wind and interconnection | EirGrid Group Open Data Licence: free to copy, adapt and use commercially; the attribution statement is required | b | d | serving API (series_long) | Supported by EirGrid Group Data | https://www.smartgriddashboard.com/all/open-data-license/ | 2026-11-21 | improve run-01 |
| `entsoe` | ENTSO-E Transparency Platform | power prices, load, generation and cross-border flows | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | serving API (series_long, flows) | Source: ENTSO-E Transparency Platform |  |  | not read |
| `entsog` | ENTSOG Transparency Platform | gas flows and nominations | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | serving API (flows) |  |  |  | not read |
| `eurostat` | Eurostat | economic sentiment indicator | Eurostat copyright notice: re-use of statistical data for commercial or non-commercial purposes is authorised with the source acknowledged; data identified as belonging to sources other than Eurostat may not be reused commercially. The sentiment survey is a DG ECFIN series, so held at c | c | d | serving API (series_long) | Source: Eurostat | https://ec.europa.eu/eurostat/help/copyright-notice | 2026-11-21 | improve run-01 |
| `frankfurter` | Frankfurter exchange rates | daily reference rates | frankfurter.dev says the API is free and open source, blends central-bank providers and needs no key; it states no data licence or terms, so not read | d | d | serving API (series_long) |  |  |  | not read |
| `fred` | FRED, Federal Reserve Bank of St. Louis | spot prices, rates and macro series | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | serving API (series_long) |  |  |  | not read |
| `gdelt` | GDELT Project | news article events | GDELT Terms of Use: unlimited and unrestricted use, including commercial; redistribution allowed with a citation to the GDELT Project and a link | b | same | web, serving API (events) | Source: The GDELT Project, https://www.gdeltproject.org/ | https://www.gdeltproject.org/about.html | 2026-11-21 | improve run-01 |
| `gfs` | NOAA GFS via NOMADS | 2 m temperature forecasts for degree days | NWS disclaimer: NWS information is in the public domain; the data must not be presented as official government material. The NOMADS page itself states no terms, so the NWS disclaimer is what was read | b | same | web, serving API (series_long) | Source: NOAA/NCEP Global Forecast System | https://www.weather.gov/disclaimer | 2026-11-21 | improve run-01 |
| `gie` | GIE AGSI+ and ALSI+ | EU gas storage and LNG terminals | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | README chart (EU gas storage), web front page, serving API (series_long, seasonal) | GIE AGSI+/ALSI+ |  |  | not read |
| `gridstatus` | GridStatus | U.S. ISO prices and load | terms page refused a plain request (HTTP 403), so not read | d | d | serving API (series_long) |  |  |  | not read |
| `guardian` | The Guardian Open Platform | news headlines (no key set yet) | Open Platform terms: content for end users' personal and non-commercial use only, and any advertisement supplied with it must be displayed; a no-ads page cannot comply | d | same | serving API (events) |  | https://www.theguardian.com/open-platform/terms-and-conditions | 2026-11-21 | improve run-01 |
| `ibkr` | Interactive Brokers gateway | futures curves when FUTURES_SOURCE=ibkr | private use only; market-data subscriptions are not redistributable | d | same | serving API (series_long) |  |  |  | not read |
| `jodi` | JODI-Oil World Database | production, demand and stocks by country | no terms page found on jodidata.org; the footer carries a copyright line only | d | d | serving API (series_long) |  |  |  | not read |
| `manual` | Manual drops: vendor exports and paid commercial data | reconstructed Brent forward curve, physical differentials | paid commercial licences (pipelines/manual_physical/NOTES.md:32); the curve is reconstructed from a vendor export (pipelines/futures/NOTES.md:199) | d | same | web /curves, serving API (series_long, curve_settles) |  |  |  | not read |
| `newsapi` | NewsAPI | headline search, on demand | NewsAPI terms: the free Developer plan is for development and testing only, never staging or production; production use needs a paid plan | d | same | serving API (events) |  | https://newsapi.org/terms | 2026-11-21 | improve run-01 |
| `ofac` | OFAC sanctions lists | Specially Designated Nationals list | the Treasury site-policies page carries no re-use statement for list data, so not read as permission | d | same | web, serving API (sanctions, events) |  |  |  | not read |
| `opec_momr` | OPEC Monthly Oil Market Report | secondary-source output tables | README reading kept pending I-06: free public data, no attribution requirement found. Not read at source by this run. The owner's register reads it as d | a | d | serving API (series_long) | Source: OPEC Monthly Oil Market Report |  |  | not read |
| `open_meteo` | Open-Meteo | observed weather and degree days | Terms of Use: the free API is for non-commercial use only, under 10,000 calls a day; data under CC BY 4.0 | c | same | web, serving API (series_long) | Weather data by Open-Meteo.com (CC BY 4.0) | https://open-meteo.com/en/terms | 2026-11-21 | improve run-01 |
| `open_meteo_forecast` | Open-Meteo forecasts | forecast weather, degree days and wind | Terms of Use: the free API is for non-commercial use only, under 10,000 calls a day; data under CC BY 4.0 | c | same | web, serving API (series_long) | Weather data by Open-Meteo.com (CC BY 4.0) | https://open-meteo.com/en/terms | 2026-11-21 | improve run-01 |
| `polymarket` | Polymarket | event market quotes | terms not read here; the owner's register reads the Terms of Use as barring redistribution | d | d | serving API (events, series_long) |  |  |  | not read |
| `reddit` | Reddit | post counts and sentiment | terms not read | d | same | serving API (events, series_long) |  |  |  | not read |
| `stocktwits` | StockTwits | post counts and sentiment | terms not read | d | same | serving API (events, series_long) |  |  |  | not read |
| `yfinance` | Yahoo Finance | continuous front-month closes for five roots | Yahoo's terms restrict redistribution (pipelines/futures/NOTES.md:330), and the question for the public site was never answered | d | same | web front page, /prices and /curves, serving API (series_long, seasonal) |  |  |  | not read |

## Derived series

A `derived` series takes the worst class among the sources its inputs come from. An id that matches no row here is class d.

| series id pattern | inputs | class |
|---|---|---|
| `^derived\.ma\.` | yfinance | d |
| `^derived\.cushing\.` | eia | b |
| `^derived\.inv\.` | eia | b |
| `^derived\.cot\.` | cftc | b |
| `^derived\.crack\..+\.spot$` | fred | a |
| `^derived\.crack\..+\.m\d$` | eia | b |
| `^derived\.(spread|curve)\.(cl|rb|ho|hu)\.` | eia | b |
| `^derived\.pos\.` | eia, cftc | b |

## Series kept off the serving layer whatever their source

- `^fut\.[a-z0-9]+\.f\d{2}\.close$`
- `^derived\.ma\.`
- `^eex\.`
- `^derived\.eu_carbon\.(price|balance)\.`
