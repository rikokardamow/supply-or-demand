import { VesselMap } from "@/components/map/VesselMap";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchVessels } from "@/data/queries/vessels";
import { isStale } from "@/data/staleness";
import { formatNumber } from "@/lib/format";

/**
 * Vessels (Spec 11): latest AIS positions inside the monitored chokepoints and
 * anchorages.
 *
 * Two honesty clauses travel with this screen, both from Spec 11 itself:
 * aisstream.io is a *terrestrial* receiver network, so coastal and chokepoint coverage is
 * good while open ocean is patchy — an empty sea here means no receiver, not no ships;
 * and the ship class is the AIS type code the crew entered, which is frequently wrong or
 * missing. Neither is a defect to fix, and both must stay visible.
 */
export const revalidate = 3600;

export default async function VesselsPage() {
  const [vessels, publish] = await Promise.all([
    fetchVessels(),
    fetchLatestPublishBy("vessel_latest", "ais"),
  ]);

  const byClass = vessels.reduce<Record<string, number>>((acc, v) => {
    const key = v.ship_type ?? "other";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        active="/vessels"
        title="Vessels"
        dek={
          <>
            {formatNumber(vessels.length, 0)} vessels seen in the monitored
            chokepoints and anchorages, of which{" "}
            {formatNumber(byClass.crude ?? 0, 0)} report as tankers
          </>
        }
      />

      <main>
        <Panel
          title="Latest positions"
          asOf={publish?.as_of ?? null}
          stale={isStale("ais", publish?.as_of)}
          pipeline={"ais"}
          sourceNote="aisstream.io terrestrial AIS. Coverage is good at coasts and chokepoints and patchy in open ocean, so an empty stretch of sea means no receiver rather than no ships. Ship class is the type code the vessel reports, not a verified classification."
        >
          {vessels.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>
              No vessel positions published. Run the ingester, then the
              compactor.
            </p>
          ) : (
            <VesselMap vessels={vessels} />
          )}
        </Panel>
      </main>
    </>
  );
}
