import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { Masthead } from "@/components/chrome/Masthead";
import { Panel } from "@/components/chrome/Panel";
import { HeatTable } from "@/components/tables/HeatTable";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeasonalBand } from "@/data/queries/seasonal";
import { fetchSeries } from "@/data/queries/series";
import { fetchWpsrLines } from "@/data/queries/wpsr";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";
import { formatDate } from "@/lib/format";
import { ChartControls } from "@/components/charts/ChartControls";

/**
 * Balances (Spec 33.02).
 *
 * A server component: every Supabase read happens on the server and the rows arrive as
 * props, so the browser issues no query for panels that change once a week. ISR at one
 * hour is the fallback; `POST /api/revalidate?tag=…` refreshes it the moment a pipeline
 * publishes.
 *
 * Both panels take their as-of from `publish_log` **filtered to the pipeline that wrote
 * them** — `serving.seasonal` is published by both wpsr and gie, so the table-level view
 * would show whichever ran last.
 */
export const revalidate = 3600;

// US crude stocks excluding the SPR -- the number this report is read for.
const SERIES = "WCESTUS1";
const PIPELINE = "wpsr";

// The other three stock lines the report is read for, each with its own seasonal band.
const CUSHING = "W_EPC0_SAX_YCUOK_MBBL";
const GASOLINE = "WGTSTUS1";
const DISTILLATE = "WDISTUS1";

const RUNS = {
  WPULEUS3: "Refinery utilisation",
};

const TRADE = {
  WCRFPUS2: "Crude production",
  WCREXUS2: "Crude exports",
  WCEIMUS2: "Crude imports",
};

export default async function BalancesPage() {
  const [
    band,
    cushingBand,
    gasolineBand,
    distillateBand,
    runs,
    trade,
    lines,
    seasonalPublish,
    linesPublish,
  ] = await Promise.all([
    fetchSeasonalBand(SERIES),
    fetchSeasonalBand(CUSHING),
    fetchSeasonalBand(GASOLINE),
    fetchSeasonalBand(DISTILLATE),
    fetchSeries(Object.keys(RUNS), 5),
    fetchSeries(Object.keys(TRADE), 5),
    fetchWpsrLines(),
    fetchLatestPublishBy("seasonal", PIPELINE),
    fetchLatestPublishBy("wpsr_lines", PIPELINE),
  ]);

  const unit = band.find((r) => r.unit)?.unit ?? null;
  const bandYears = band.find((r) => r.years)?.years ?? null;
  const weekEnding = lines.find((r) => r.week_ending)?.week_ending ?? null;

  return (
    <main>
      <Masthead active="/balances" />

      <h2
        style={{
          fontFamily: "var(--heading-stack)",
          fontSize: "1.6rem",
          margin: "0.5rem 0 0.35rem",
        }}
      >
        Balances
      </h2>
      <p
        style={{
          color: "var(--muted)",
          fontSize: "0.82rem",
          margin: "0 0 1.6rem",
        }}
      >
        EIA Weekly Petroleum Status Report
        {weekEnding ? ` · week ending ${formatDate(weekEnding)}` : ""}
      </p>

      <Panel
        title="At a glance"
        asOf={linesPublish?.as_of ?? null}
        stale={isStale(PIPELINE, linesPublish?.as_of)}
        sourceNote={
          "Week-on-week is an absolute change in each line's own unit; year-on-year and " +
          "vs-median are percentages. The seasonal median excludes 2020."
        }
      >
        <HeatTable rows={lines} />
      </Panel>

      <Panel
        title="US crude oil stocks, excluding the SPR"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote={
          seasonalPublish?.source_note ??
          "EIA Weekly Petroleum Status Report, via serving.seasonal_v"
        }
      >
        {band.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>
            No seasonal band published for {SERIES} yet.
          </p>
        ) : (
          <SeasonalChart rows={band} unit={unit} bandYears={bandYears} />
        )}
      </Panel>

      <Panel
        title="Crude oil at Cushing, Oklahoma"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote="The WTI delivery point: the tank farm the front-month contract settles against, which is why its fill matters out of proportion to its size."
      >
        <SeasonalChart
          rows={cushingBand}
          unit={cushingBand.find((r) => r.unit)?.unit ?? null}
          bandYears={cushingBand.find((r) => r.years)?.years ?? null}
        />
      </Panel>

      <Panel
        title="Total motor gasoline stocks"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote="Seven-year range and median, 2020 excluded."
      >
        <SeasonalChart
          rows={gasolineBand}
          unit={gasolineBand.find((r) => r.unit)?.unit ?? null}
          bandYears={gasolineBand.find((r) => r.years)?.years ?? null}
        />
      </Panel>

      <Panel
        title="Distillate fuel oil stocks"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote="Diesel and heating oil. Seven-year range and median, 2020 excluded."
      >
        <SeasonalChart
          rows={distillateBand}
          unit={distillateBand.find((r) => r.unit)?.unit ?? null}
          bandYears={distillateBand.find((r) => r.years)?.years ?? null}
        />
      </Panel>

      <Panel
        title="Refinery utilisation"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote="Per cent of operable capacity. Sustained readings near 100% leave no slack for an unplanned outage."
      >
        <ChartControls lines={toLines(runs, RUNS)} unit={commonUnit(runs)} />
      </Panel>

      <Panel
        title="Crude production, exports and imports"
        asOf={seasonalPublish?.as_of ?? null}
        stale={isStale(PIPELINE, seasonalPublish?.as_of)}
        sourceNote="All three on one axis in thousand barrels per day, so the balance between them is readable directly."
      >
        <ChartControls lines={toLines(trade, TRADE)} unit={commonUnit(trade)} />
      </Panel>
    </main>
  );
}
