import { ChartControls } from "@/components/charts/ChartControls";
import { PositioningChart } from "@/components/charts/PositioningChart";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import {
  CONTRACTS,
  POSITIONING_SERIES,
  positioningBook,
  netLengthLines,
  netShareLines,
} from "@/data/positioning";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { formatNumber } from "@/lib/format";

/**
 * Positioning: what the CFTC's Commitments of Traders report says speculators are holding.
 *
 * Four energy contracts, from `pipelines/cftc` — WTI, Brent, RBOB and heating oil, on the
 * disaggregated futures-only report. The screen is built around the managed money
 * category because that is the one that trades on a view; producer/merchant is hedging
 * against physical and its net is close to the mirror image by construction.
 *
 * **Every figure here is three days stale the moment it is published, and that is the
 * report, not the pipeline.** COT is stamped on the Tuesday and released the following
 * Friday at 15:30 ET, so the freshest possible reading describes a book that has had
 * three sessions to change. The cadence line under the as-of date says so on every panel.
 */
export const revalidate = 3600;

const PIPELINE = "cftc";

export default async function PositioningPage() {
  const [rows, publish] = await Promise.all([
    fetchSeries(POSITIONING_SERIES, 10),
    fetchLatestPublishBy("series_long", PIPELINE),
  ]);

  const stale = isStale(PIPELINE, publish?.as_of);
  const asOf = publish?.as_of ?? null;

  const net = netLengthLines(rows);
  const latestWti = net.find((line) => line.name === "WTI")?.y.at(-1) ?? null;

  return (
    <>
      <PageHeader
        active="/positioning"
        title="Positioning"
        dek="CFTC Commitments of Traders — managed money in the four NYMEX energy contracts"
      />

      <main>
        <Panel
          title="Managed money net length"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote={
            "Long minus short, in contracts, from the disaggregated futures-only report. " +
            "The gross long leg on its own overstates conviction by however large the " +
            "short leg happens to be, which is why the net is what the trade quotes. " +
            "Brent here is NYMEX Brent Last Day (BZ), not ICE Brent -- the CFTC only " +
            "collects from US-regulated exchanges, and ICE Brent reports to the FCA." +
            (latestWti !== null && latestWti !== undefined
              ? ` Managed money is net ${formatNumber(Math.abs(latestWti), 0)} contracts ` +
                `${latestWti >= 0 ? "long" : "short"} of WTI.`
              : "")
          }
        >
          <ChartControls lines={net} unit="contracts" height={380} />
        </Panel>

        <Panel
          title="Managed money net as a share of open interest"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="WTI's open interest dwarfs heating oil's, so a net figure in lots says more about the size of the contract than about how stretched positioning is. As a share of the open interest it sits in, the four are comparable."
        >
          <ChartControls lines={netShareLines(rows)} unit="%" height={380} />
        </Panel>

        {(Object.keys(CONTRACTS) as (keyof typeof CONTRACTS)[]).map((root) => (
          <Panel
            key={root}
            title={`${CONTRACTS[root].label} — managed money legs against open interest`}
            asOf={asOf}
            stale={stale}
            pipeline={PIPELINE}
            sourceNote={
              `${CONTRACTS[root].market}. Long above the axis, short below it, and the ` +
              `open interest they sit in on the right. Bars rather than lines because ` +
              `the CFTC counts the book once a week and there is nothing in between: a ` +
              `line joining the counts would draw a path the position never took. A net ` +
              `that has not moved can hide both legs growing together, which is a ` +
              `different market from one where nobody has a position.`
            }
          >
            <PositioningChart data={positioningBook(rows, root)} height={320} />
          </Panel>
        ))}
      </main>
    </>
  );
}
