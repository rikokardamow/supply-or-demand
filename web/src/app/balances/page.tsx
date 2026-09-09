import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { Masthead } from "@/components/chrome/Masthead";
import { Panel } from "@/components/chrome/Panel";
import { fetchLatestPublish } from "@/data/queries/publishLog";
import { fetchSeasonalBand } from "@/data/queries/seasonal";

/**
 * Balances (Spec 33.02), Session A scope: the chrome plus one real seasonal panel drawn
 * from `serving.seasonal_v`. The WPSR heat table and the remaining charts are Session B.
 *
 * A server component: the Supabase read happens on the server and the rows arrive at the
 * chart as props, so the browser never issues a query for a panel that changes weekly.
 * ISR at one hour is the fallback cadence Spec 33 §6 specifies; the pipelines will call
 * `/api/revalidate` on publish once that route exists.
 */
export const revalidate = 3600;

// US crude stocks excluding the SPR -- the single number this report is read for.
const SERIES = "WCESTUS1";

export default async function BalancesPage() {
  const [rows, publish] = await Promise.all([
    fetchSeasonalBand(SERIES),
    fetchLatestPublish("seasonal"),
  ]);

  const unit = rows.find((r) => r.unit)?.unit ?? null;
  const bandYears = rows.find((r) => r.years)?.years ?? null;

  return (
    <main>
      <Masthead active="/balances" />

      <h2
        style={{
          fontFamily: "var(--heading-stack)",
          fontSize: "1.6rem",
          margin: "0.5rem 0 1.4rem",
        }}
      >
        Balances
      </h2>

      <Panel
        title="US crude oil stocks, excluding the SPR"
        asOf={publish?.as_of ?? null}
        sourceNote={
          publish?.source_note ??
          "EIA Weekly Petroleum Status Report, via serving.seasonal_v"
        }
      >
        {rows.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>
            No seasonal band published for {SERIES} yet.
          </p>
        ) : (
          <SeasonalChart rows={rows} unit={unit} bandYears={bandYears} />
        )}
      </Panel>
    </main>
  );
}
