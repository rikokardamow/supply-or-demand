import { ChartControls } from "@/components/charts/ChartControls";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import {
  BALANCE_SERIES,
  CRACK_SERIES,
  balanceCheckLines,
  balanceComponentLines,
  crudeBalance,
  daysOfCoverLine,
  pairLines,
} from "@/data/oilMath";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";
import { formatNumber } from "@/lib/format";

/**
 * Oil math: the barrel accounting behind the weekly report.
 *
 * Everything here is arithmetic on series the lake already holds — EIA's WPSR and the
 * cracks `pipelines/derived/cracks.py` computes. Nothing is published for this screen; the
 * balance, the adjustment and days of cover are all read-time transforms.
 *
 * The screen exists because the WPSR headline everyone quotes — "crude stocks fell 4.4
 * million barrels" — is one line of an identity with five other terms, and which term
 * moved is the whole question.
 */
export const revalidate = 3600;

const PIPELINE = "wpsr";

export default async function OilMathPage() {
  const [rows, cracks, publish, crackPublish] = await Promise.all([
    fetchSeries(BALANCE_SERIES, 5),
    fetchSeries(Object.keys(CRACK_SERIES), 5),
    fetchLatestPublishBy("series_long", PIPELINE),
    fetchLatestPublishBy("series_long", "derived"),
  ]);

  const stale = isStale(PIPELINE, publish?.as_of);
  const asOf = publish?.as_of ?? null;

  const weeks = crudeBalance(rows);
  const latest = weeks.at(-1);
  const cover = daysOfCoverLine(rows);
  const latestCover = cover[0]?.y.at(-1) ?? null;

  return (
    <>
      <PageHeader
        active="/oil-math"
        title="Oil math"
        dek="The weekly US crude balance, where it fails to close, and what the refining margin is doing"
      />

      <main>
        {/* The standfirst. A page of six charts needs one paragraph saying why the
            arithmetic is worth doing at all, and the elasticities are the reason: they are
            what turns a weekly American survey into a global price signal. */}
        <section
          className="term-panel"
          style={{
            padding: "var(--space-5)",
            marginBottom: "var(--space-6)",
            borderLeft: "3px solid var(--accent)",
          }}
        >
          <p
            style={{
              fontSize: "var(--size-lead)",
              lineHeight: 1.65,
              maxWidth: "72ch",
            }}
          >
            Oil moves violently because almost nothing about it responds to
            price in the short run. A demand elasticity near{" "}
            <span className="tabular">&minus;0.06</span> and a supply elasticity
            near <span className="tabular">0.04</span> mean a 5% loss of supply
            needs something close to an 85% move in price to clear the market,
            where fresh tomatoes would need about 1%. That is why a weekly
            American stock survey moves a global benchmark, and why it is worth
            taking apart. The headline everyone quotes &mdash; crude stocks fell
            4.4 million barrels &mdash; is one line of a six-term identity, and
            which term moved is the entire question: a draw built on hard
            refinery runs is a different market from one built on collapsed
            imports, and the two point opposite ways. So the components below
            are drawn with their signs, the change they imply is checked against
            the change actually reported, and the barrels the identity cannot
            place are shown rather than quietly absorbed. Stocks are then read
            as days of cover rather than as a barrel count, because refining
            capacity has grown and the same barrel no longer buys the same
            comfort.
          </p>
        </section>

        <Panel
          title="The crude balance, week by week"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote={
            "Production and imports add barrels; exports and refinery runs remove them, so " +
            "both are drawn negative. The gap between the two sides is the build or draw " +
            "the identity implies. All four are thousand barrels per day as EIA reports " +
            "them." +
            (latest?.implied !== null && latest?.implied !== undefined
              ? ` In the week to ${new Date(latest.ts).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })} the components imply a ${latest.implied >= 0 ? "build" : "draw"} of ${formatNumber(Math.abs(latest.implied), 0)} MBBL/D.`
              : "")
          }
        >
          <ChartControls
            lines={balanceComponentLines(weeks)}
            unit="MBBL/D"
            height={360}
            defaultRange="1Y"
          />
        </Panel>

        <Panel
          title="Where the balance fails to close"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote={
            "The identity is Δ(commercial + SPR stocks) = production + imports − exports − " +
            "refinery runs + adjustment. The SPR sits on the left-hand side rather than " +
            "being omitted: a release moves barrels out of the reserve and into commercial " +
            "tanks, and leaving it out would charge the whole transfer to the adjustment. " +
            "That adjustment is not a rounding error — EIA publishes it as a line of its " +
            "own because the components come from different surveys with different " +
            "coverage, and it has run persistently positive since about 2015." +
            (latest?.adjustment !== null && latest?.adjustment !== undefined
              ? ` The latest week leaves ${formatNumber(latest.adjustment, 0)} MBBL/D unaccounted for.`
              : "")
          }
        >
          <ChartControls
            lines={balanceCheckLines(weeks)}
            unit="MBBL/D"
            height={340}
            defaultRange="1Y"
          />
        </Panel>

        <Panel
          title="Days of cover"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote={
            "Commercial crude stocks divided by the rate refineries are running them. The " +
            "headline stock measure ahead of the barrel count: an absolute level drifts " +
            "with structural growth in refining capacity, so the same 400 million barrels " +
            "means different things in 1990 and today. The SPR is excluded — it is not " +
            "available to refiners week to week, and including it would overstate cover by " +
            "roughly a fortnight." +
            (latestCover !== null && latestCover !== undefined
              ? ` Latest ${formatNumber(latestCover, 1)} days.`
              : "")
          }
        >
          <ChartControls lines={cover} unit="days" height={320} />
        </Panel>

        <Panel
          title="Refinery utilisation against crude runs"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="Utilisation is a percentage of operable capacity and runs are a rate, so the two sit on separate axes. Read together they separate a refinery system running hard from one that has simply added capacity: runs can rise while utilisation falls."
        >
          <ChartControls
            lines={pairLines(rows, [
              { id: "WCRRIUS2", name: "Refiner net input of crude" },
              { id: "WPULEUS3", name: "Utilisation", secondary: true },
            ])}
            unit="MBBL/D"
            secondaryUnit="%"
            height={340}
          />
        </Panel>

        <Panel
          title="Products supplied"
          asOf={asOf}
          stale={stale}
          pipeline={PIPELINE}
          sourceNote="EIA's proxy for demand: product leaving the primary distribution system, not product burned. It measures barrels shipped to wholesalers, so a week of restocking reads as demand and a week of destocking hides it — which is why it is noisy week to week and only meaningful on a four-week average."
        >
          <ChartControls
            lines={pairLines(rows, [
              { id: "WRPUPUS2", name: "Total products supplied" },
              { id: "WGFUPUS2", name: "Motor gasoline" },
              { id: "WDIUPUS2", name: "Distillate" },
            ])}
            unit="MBBL/D"
            height={340}
          />
        </Panel>

        <Panel
          title="Refining margins"
          asOf={crackPublish?.as_of ?? null}
          stale={isStale("derived", crackPublish?.as_of)}
          pipeline="derived"
          sourceNote={
            "A refiner is naturally long this margin — it buys crude and sells products — " +
            "and the futures position that locks it in is long crude and short products. " +
            "Stated as legs rather than as 'long the crack', which half an audience reads " +
            "backwards. The 3-2-1 ratio is the market's shared reference and roughly " +
            "matches a US refinery's yield; it is a convention, not an optimum, so the " +
            "gap between it and the single-product cracks is the signal about yield " +
            "economics. Gasoline and distillate margins peak in different seasons — " +
            "compare each against its own history, never against each other's."
          }
        >
          <ChartControls
            lines={toLines(cracks, CRACK_SERIES)}
            unit={commonUnit(cracks)}
            height={340}
          />
        </Panel>
      </main>
    </>
  );
}
