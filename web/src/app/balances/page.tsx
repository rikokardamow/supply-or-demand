import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { Masthead } from "@/components/chrome/Masthead";
import { Panel } from "@/components/chrome/Panel";
import { HeatTable } from "@/components/tables/HeatTable";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeasonalBand } from "@/data/queries/seasonal";
import { fetchWpsrLines } from "@/data/queries/wpsr";
import { isStale } from "@/data/staleness";
import { formatDate } from "@/lib/format";

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

export default async function BalancesPage() {
  const [band, lines, seasonalPublish, linesPublish] = await Promise.all([
    fetchSeasonalBand(SERIES),
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
    </main>
  );
}
