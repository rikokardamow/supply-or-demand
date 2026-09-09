import { ChartControls } from "@/components/charts/ChartControls";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";

/**
 * Supply: drilling activity, US monthly production and crude cost, the OPEC balance, and
 * JODI stocks.
 *
 * The sources here have very different depth and the panels say so rather than
 * presenting them alike. EIA's monthly series run back to the 1970s; Baker Hughes is
 * weekly with a real run; OPEC's MOMR tables are a rolling forecast window parsed from
 * each month's PDF, and JODI arrives as a handful of recent months.
 */
export const revalidate = 3600;

const US_RIGS = {
  "bh.rigs.united_states.oil": "US oil",
  "bh.rigs.united_states.gas": "US gas",
  "bh.rigs.united_states.total": "US total",
};

const CANADA_RIGS = {
  "bh.rigs.canada.oil": "Canada oil",
  "bh.rigs.canada.gas": "Canada gas",
  "bh.rigs.canada.total": "Canada total",
};

// EIA monthly, back to 1997. Production dwarfs exports, so they share a chart but not an
// axis -- on one scale the export line would sit flat against the floor.
const GAS_SUPPLY = {
  N9070US2: "Dry gas production",
  N9133US2: "LNG exports",
};

// Refiner acquisition cost, monthly since 1974. The domestic/imported split is the one
// that moves with the quality and freight story rather than with flat price.
const CRUDE_COST = {
  R0000____3: "Composite",
  R1200____3: "Domestic",
  R1300____3: "Imported",
};

// Landed cost of imported crude by API gravity band, monthly since 1983 -- the spread
// between the bands is the light/heavy differential in its rawest published form.
const LANDED_BY_GRAVITY = {
  I000000208: "20–24.9° API",
  I000000258: "25–29.9° API",
  I000000308: "30–34.9° API",
  I000000358: "35–39.9° API",
  I000000408: "40–44.9° API",
};

// Gas delivered to end users, monthly since 1973 -- the longest run in this lake.
const GAS_CONSUMPTION = {
  N3010US2: "Residential",
  N3020US2: "Commercial",
};

// OPEC's headline balance table. Twelve quarters now, spanning 2025 Q1 to 2027 Q4 --
// past and forecast -- because pull_momr_history.py backfilled fifteen monthly issues.
// Before that backfill only the current issue's forward window existed, which is why
// this panel had eight forecast quarters and nothing behind them.
const OPEC_DEMAND = {
  "momr.demand_balance.world_demand.a_total_world_demand.quarterly":
    "World demand",
  "momr.demand_balance.world_demand.americas.quarterly": "Americas",
  "momr.demand_balance.world_demand.asia_pacific.quarterly": "Asia-Pacific",
  "momr.demand_balance.world_demand.europe.quarterly": "Europe",
};

const OPEC_SUPPLY = {
  "momr.demand_balance.nondoc_liquids_production.total_nondoc_liquids_production.quarterly":
    "Total non-DoC liquids",
  "momr.demand_balance.nondoc_liquids_production.of_which_us.quarterly":
    "of which US",
  "momr.demand_balance.nondoc_liquids_production.doc_ngls.quarterly":
    "DoC NGLs",
  "momr.demand_balance.nondoc_liquids_production.processing_gains.quarterly":
    "Processing gains",
};

const JODI_STOCKS = {
  "jodi.closing_stocks.us": "United States",
  "jodi.closing_stocks.ca": "Canada",
  "jodi.closing_stocks.gb": "United Kingdom",
  "jodi.closing_stocks.no": "Norway",
};

export default async function SupplyPage() {
  const [
    usRigs,
    caRigs,
    gasSupply,
    crudeCost,
    landed,
    gasConsumption,
    opecDemand,
    opecSupply,
    jodi,
    rigPublish,
    eiaPublish,
    opecPublish,
    jodiPublish,
  ] = await Promise.all([
    fetchSeries(Object.keys(US_RIGS), 5),
    fetchSeries(Object.keys(CANADA_RIGS), 5),
    fetchSeries(Object.keys(GAS_SUPPLY), 15),
    fetchSeries(Object.keys(CRUDE_COST), 15),
    fetchSeries(Object.keys(LANDED_BY_GRAVITY), 15),
    fetchSeries(Object.keys(GAS_CONSUMPTION), 15),
    fetchSeries(Object.keys(OPEC_DEMAND), 6),
    fetchSeries(Object.keys(OPEC_SUPPLY), 6),
    fetchSeries(Object.keys(JODI_STOCKS), 5),
    fetchLatestPublishBy("series_long", "baker_hughes"),
    fetchLatestPublishBy("series_long", "eia"),
    fetchLatestPublishBy("series_long", "opec_momr"),
    fetchLatestPublishBy("series_long", "jodi"),
  ]);

  const eiaAsOf = eiaPublish?.as_of ?? null;
  const eiaStale = isStale("eia", eiaAsOf);
  const opecAsOf = opecPublish?.as_of ?? null;
  const opecStale = isStale("opec_momr", opecAsOf);

  return (
    <>
      <PageHeader
        active="/supply"
        title="Supply"
        dek="Drilling activity, US monthly production and crude cost, the OPEC balance and JODI stocks"
      />

      <main>
        <Panel
          title="United States rig count"
          asOf={rigPublish?.as_of ?? null}
          stale={isStale("baker_hughes", rigPublish?.as_of)}
          sourceNote="Baker Hughes, weekly. Rigs lead production by roughly six months, which is why the count is read as a forward indicator rather than a current one."
        >
          <ChartControls
            lines={toLines(usRigs, US_RIGS)}
            unit={commonUnit(usRigs)}
          />
        </Panel>

        <Panel
          title="Canada rig count"
          asOf={rigPublish?.as_of ?? null}
          stale={isStale("baker_hughes", rigPublish?.as_of)}
          sourceNote="Baker Hughes, weekly. Canadian activity swings hard with spring break-up, when thawing ground halts rig movement — the annual collapse is seasonal, not a signal."
        >
          <ChartControls
            lines={toLines(caRigs, CANADA_RIGS)}
            unit={commonUnit(caRigs)}
          />
        </Panel>

        <Panel
          title="US dry gas production and LNG exports"
          asOf={eiaAsOf}
          stale={eiaStale}
          sourceNote="EIA monthly, since 1997. Separate axes: production runs several times the export volume, and on one scale the export line would sit flat against the floor. Feedgas has no distinct EIA series, so exports are the only published measure of the LNG pull."
        >
          <ChartControls
            lines={toLines(gasSupply, GAS_SUPPLY, { secondary: ["N9133US2"] })}
            unit="MMcf — production"
            secondaryUnit="MMcf — exports"
          />
        </Panel>

        <Panel
          title="Refiner acquisition cost of crude oil"
          asOf={eiaAsOf}
          stale={eiaStale}
          sourceNote="EIA monthly, since 1974 — what US refiners actually paid, rather than a marker price. The gap between domestic and imported carries the quality and freight story that a single benchmark hides."
        >
          <ChartControls
            lines={toLines(crudeCost, CRUDE_COST)}
            unit={commonUnit(crudeCost)}
          />
        </Panel>

        <Panel
          title="Landed cost of imported crude by API gravity"
          asOf={eiaAsOf}
          stale={eiaStale}
          sourceNote="EIA monthly, since 1983. The spread between bands is the light/heavy differential in its rawest published form: heavier barrels land cheaper, and the width of that gap is a refining-margin signal in itself."
        >
          <ChartControls
            lines={toLines(landed, LANDED_BY_GRAVITY)}
            unit={commonUnit(landed)}
          />
        </Panel>

        <Panel
          title="US gas delivered to residential and commercial users"
          asOf={eiaAsOf}
          stale={eiaStale}
          sourceNote="EIA monthly, since 1973 — the longest continuous run in this lake. The seasonal amplitude is heating demand, and its year-on-year change is a cleaner weather signal than temperature itself."
        >
          <ChartControls
            lines={toLines(gasConsumption, GAS_CONSUMPTION)}
            unit={commonUnit(gasConsumption)}
          />
        </Panel>

        <Panel
          title="OPEC world oil demand forecast"
          asOf={opecAsOf}
          stale={opecStale}
          sourceNote="OPEC Monthly Oil Market Report, quarterly. Built from fifteen monthly Excel appendices back to March 2025, so the series carries past quarters as well as OPEC's forward view. Six months in that range are not served by OPEC at all and are named in the pipeline's own log rather than interpolated."
        >
          {opecDemand.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>
              No OPEC demand forecast published.
            </p>
          ) : (
            <ChartControls
              lines={toLines(opecDemand, OPEC_DEMAND)}
              unit={commonUnit(opecDemand)}
            />
          )}
        </Panel>

        <Panel
          title="OPEC non-DoC liquids supply forecast"
          asOf={opecAsOf}
          stale={opecStale}
          sourceNote="Supply from outside the Declaration of Cooperation — the barrels OPEC+ does not control, and the ones its own balance treats as given. US shale is the swing component within it."
        >
          {opecSupply.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>
              No OPEC supply forecast published.
            </p>
          ) : (
            <ChartControls
              lines={toLines(opecSupply, OPEC_SUPPLY)}
              unit={commonUnit(opecSupply)}
            />
          )}
        </Panel>

        <Panel
          title="JODI closing stocks"
          asOf={jodiPublish?.as_of ?? null}
          stale={isStale("jodi", jodiPublish?.as_of)}
          sourceNote="Joint Organisations Data Initiative, monthly, self-reported by each country. Coverage and revision practice vary by reporter, so levels are more comparable within a country over time than across countries."
        >
          {jodi.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No JODI stocks published.</p>
          ) : (
            <ChartControls
              lines={toLines(jodi, JODI_STOCKS)}
              unit={commonUnit(jodi)}
            />
          )}
        </Panel>
      </main>
    </>
  );
}
