import { ChartControls } from "@/components/charts/ChartControls";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import {
  MARINE_CORRIDORS,
  PIPELINE_CORRIDORS,
  RAIL_CORRIDORS,
  corridorLines,
  modeTotals,
  netLine,
} from "@/data/paddFlows";
import { fetchFlows } from "@/data/queries/flows";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { isStale } from "@/data/staleness";
import { formatDate } from "@/lib/format";

/**
 * Flows (PADD): where US crude physically moves, and by what.
 *
 * The five Petroleum Administration for Defense Districts are the geography EIA still
 * reports crude movements on, and the movements between them are the closest thing the
 * weekly balance has to a map. `serving.flows` holds them back to 1986 by pipeline and
 * tanker or barge, and to 2010 by rail.
 *
 * **Modes are kept apart, never summed.** The mode is where the story usually is: Bakken
 * crude moved east and west by rail because there was no pipe to carry it, and stopped
 * when there was. A chart that added rail to pipeline would show a smooth total and hide
 * the substitution entirely.
 */
export const revalidate = 3600;

const PIPELINE = "flows";

export default async function FlowsPage() {
  const [rows, publish] = await Promise.all([
    fetchFlows("eia", ["pipeline", "rail", "tanker_barge"]),
    fetchLatestPublishBy("flows", PIPELINE),
  ]);

  const stale = isStale(PIPELINE, publish?.as_of);
  const asOf = publish?.as_of ?? null;

  // `serving.flows` holds three sources under one pipeline, and `publish_log` records the
  // newest of them -- hourly RTO grid interchange, which is days old. The inter-PADD
  // series on this page is monthly and runs months behind that. The badge keeps the
  // publish provenance, as every other panel does; the dek states the month these charts
  // actually reach, so nobody reads a September stamp as September data.
  const latestMonth = rows.reduce<string | null>(
    (newest, row) => (newest === null || row.ts > newest ? row.ts : newest),
    null,
  );

  return (
    <>
      <PageHeader
        active="/flows"
        title="Flows"
        dek={
          <>
            EIA inter-PADD crude movements — by pipeline, rail and tanker or
            barge, monthly since 1986. Latest reported month{" "}
            {formatDate(latestMonth)}; EIA publishes these about two months
            behind.
          </>
        }
      />

      <main>
        <Panel
          title="Gulf Coast and Midwest, the two directions of the same pipe"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="The largest inter-PADD corridor in both directions, and the one that reversed. Gulf Coast to Midwest is the historic direction — imported crude landed at the coast and moved inland. Midwest to Gulf Coast is what shale and the Cushing glut built, and it is the leg to watch when the WTI curve moves."
        >
          <ChartControls
            lines={corridorLines(rows, "pipeline", [
              ["PADD3", "PADD2"],
              ["PADD2", "PADD3"],
            ])}
            unit="MBBL/month"
            height={340}
          />
        </Panel>

        <Panel
          title="Net movement, Midwest to Gulf Coast"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="The two legs above, netted: above zero the Midwest is a net sender and Cushing is draining south, below zero it is a net receiver. The gross legs answer how much moved; this answers which way the system leans, and they are different questions."
        >
          <ChartControls
            lines={netLine(
              rows,
              "pipeline",
              "PADD2",
              "PADD3",
              "Midwest → Gulf Coast, net",
            )}
            unit="MBBL/month"
            height={300}
          />
        </Panel>

        <Panel
          title="Pipeline corridors"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="The five live pipeline corridors by volume. Corridors whose last report predates 2020 are left out — PADD5 to PADD3 by pipeline has reported nothing since 2002, and a dead line along the axis is noise rather than information."
        >
          <ChartControls
            lines={corridorLines(rows, "pipeline", PIPELINE_CORRIDORS)}
            unit="MBBL/month"
            height={340}
          />
        </Panel>

        <Panel
          title="Crude by rail"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="Rail is the mode that appears when pipe is missing and retreats when it arrives. EIA reports no inter-PADD rail movement before 2010 because there was essentially none; the series begins where the measurement does, rather than being drawn as zero back to 1986."
        >
          <ChartControls
            lines={corridorLines(rows, "rail", RAIL_CORRIDORS)}
            unit="MBBL/month"
            height={340}
          />
        </Panel>

        <Panel
          title="Tanker and barge"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="Waterborne movements between districts, dominated by West Coast to Gulf Coast — Alaskan crude — and Gulf Coast to East Coast under the Jones Act, which requires US-built, US-crewed vessels and is why this corridor is smaller than geography alone would suggest."
        >
          <ChartControls
            lines={corridorLines(rows, "tanker_barge", MARINE_CORRIDORS)}
            unit="MBBL/month"
            height={340}
          />
        </Panel>

        <Panel
          title="Total moved by mode"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="Every corridor each mode reports, summed. Monthly totals in thousand barrels, left as EIA reports them rather than converted to a daily rate — which means February sits about a tenth below an identical January by construction."
        >
          <ChartControls
            lines={modeTotals(rows)}
            unit="MBBL/month"
            height={340}
          />
        </Panel>
      </main>
    </>
  );
}
