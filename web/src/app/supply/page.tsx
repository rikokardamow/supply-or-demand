import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { Masthead } from "@/components/chrome/Masthead";
import { Panel } from "@/components/chrome/Panel";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";

/**
 * Supply: drilling activity, the OPEC balance, and JODI stocks.
 *
 * These three sources have very different depth, and the panels say so rather than
 * presenting them alike. Baker Hughes is weekly with a real run of history; OPEC's MOMR
 * tables and JODI arrive as a handful of recent points each, because both are parsed from
 * monthly publications rather than an API with an archive.
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

const OPEC_BALANCE = {
  "momr.demand_balance.nondoc_liquids_production.total_liquids_production.quarterly":
    "Total liquids production",
  "momr.demand_balance.nondoc_liquids_production.total_nondoc_liquids_production.quarterly":
    "Non-DoC liquids production",
  "momr.demand_balance.nondoc_liquids_production.opec_crude_oil_production_secondary_sources.quarterly":
    "OPEC crude (secondary sources)",
};

const JODI_STOCKS = {
  "jodi.closing_stocks.us": "United States",
  "jodi.closing_stocks.ca": "Canada",
  "jodi.closing_stocks.gb": "United Kingdom",
  "jodi.closing_stocks.no": "Norway",
};

export default async function SupplyPage() {
  const [usRigs, caRigs, opec, jodi, rigPublish, opecPublish, jodiPublish] =
    await Promise.all([
      fetchSeries(Object.keys(US_RIGS), 5),
      fetchSeries(Object.keys(CANADA_RIGS), 5),
      fetchSeries(Object.keys(OPEC_BALANCE), 5),
      fetchSeries(Object.keys(JODI_STOCKS), 5),
      fetchLatestPublishBy("series_long", "baker_hughes"),
      fetchLatestPublishBy("series_long", "opec_momr"),
      fetchLatestPublishBy("series_long", "jodi"),
    ]);

  return (
    <main>
      <Masthead active="/supply" />

      <h2
        style={{
          fontFamily: "var(--heading-stack)",
          fontSize: "1.6rem",
          margin: "0.5rem 0 0.35rem",
        }}
      >
        Supply
      </h2>
      <p style={{ color: "var(--muted)", fontSize: "0.82rem", margin: "0 0 1.6rem" }}>
        Drilling activity, the OPEC balance and JODI closing stocks
      </p>

      <Panel
        title="United States rig count"
        asOf={rigPublish?.as_of ?? null}
        stale={isStale("baker_hughes", rigPublish?.as_of)}
        sourceNote="Baker Hughes, weekly. Rigs lead production by roughly six months, which is why the count is read as a forward indicator rather than a current one."
      >
        <TimeSeriesChart lines={toLines(usRigs, US_RIGS)} unit={commonUnit(usRigs)} />
      </Panel>

      <Panel
        title="Canada rig count"
        asOf={rigPublish?.as_of ?? null}
        stale={isStale("baker_hughes", rigPublish?.as_of)}
        sourceNote="Baker Hughes, weekly. Canadian activity swings hard with spring break-up, when thawing ground halts movement — the annual collapse is seasonal, not a signal."
      >
        <TimeSeriesChart lines={toLines(caRigs, CANADA_RIGS)} unit={commonUnit(caRigs)} />
      </Panel>

      <Panel
        title="OPEC liquids balance"
        asOf={opecPublish?.as_of ?? null}
        stale={isStale("opec_momr", opecPublish?.as_of)}
        sourceNote="OPEC Monthly Oil Market Report, quarterly. Only a handful of quarters are held: these tables are parsed from each month's published PDF, which carries a short forward window rather than an archive, so this is a snapshot of the current view and not a history."
      >
        {opec.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>No OPEC balance published.</p>
        ) : (
          <TimeSeriesChart lines={toLines(opec, OPEC_BALANCE)} unit={commonUnit(opec)} />
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
          <TimeSeriesChart lines={toLines(jodi, JODI_STOCKS)} unit={commonUnit(jodi)} />
        )}
      </Panel>
    </main>
  );
}
