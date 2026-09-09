import { ChartControls } from "@/components/charts/ChartControls";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import { fetchCurve, fetchSpreads } from "@/data/queries/curve";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";
import { formatDate } from "@/lib/format";
import { SERIES } from "@/theme/plotly";

/**
 * Curves (Spec 33.04): outright prices, the forward curve, and calendar spreads.
 *
 * Two very different vintages sit on this screen, and the as-of badges say so plainly.
 * Front-month closes come from Yahoo and are current; the spreads come from EIA's
 * discontinued route and stop in April 2024, while the forward curve is a single
 * reconstructed snapshot. That is the state of this project's futures data, and the
 * screen reports it rather than hiding it behind a chart that looks alive.
 */
export const revalidate = 3600;

const CRUDE = {
  "fut.cl.f01.close": "WTI",
  "fut.lco.f01.close": "Brent",
};

const PRODUCTS = {
  "fut.ho.f01.close": "Heating oil",
  "fut.rb.f01.close": "RBOB gasoline",
};

const GAS = { "fut.ng.f01.close": "Henry Hub" };

export default async function CurvesPage() {
  const [crude, products, gas, curve, spreads, pricePublish, curvePublish] =
    await Promise.all([
      fetchSeries(Object.keys(CRUDE), 5),
      fetchSeries(Object.keys(PRODUCTS), 5),
      fetchSeries(Object.keys(GAS), 5),
      fetchCurve("LCO"),
      fetchSpreads("CL", ["M1-M2", "M1-M3"]),
      fetchLatestPublishBy("series_long", "yfinance"),
      fetchLatestPublishBy("curve_settles", "curve"),
    ]);

  const spreadLines = [...new Set(spreads.map((s) => s.legs))]
    .filter((legs): legs is string => Boolean(legs))
    .map((legs) => {
      const points = spreads.filter((s) => s.legs === legs);
      return {
        name: legs,
        x: points.map((p) => p.trade_date ?? ""),
        y: points.map((p) => p.value),
      };
    });

  const tradeDate = curve.find((c) => c.trade_date)?.trade_date ?? null;

  return (
    <>
      <PageHeader
        active="/curves"
        title="Curves"
        dek="Front-month closes, the forward curve and calendar spreads"
      />

      <main>
        <Panel
          title="Crude front month"
          asOf={pricePublish?.as_of ?? null}
          stale={isStale("yfinance", pricePublish?.as_of)}
          sourceNote="Yahoo Finance continuous front-month daily closes — a last trade, not an exchange settlement. See pipelines/futures/yfinance_front.py for the measured difference."
        >
          <ChartControls
            lines={toLines(crude, CRUDE)}
            unit={commonUnit(crude)}
          />
        </Panel>

        <Panel
          title="Refined products front month"
          asOf={pricePublish?.as_of ?? null}
          stale={isStale("yfinance", pricePublish?.as_of)}
          sourceNote="NY Harbor heating oil and RBOB gasoline, both in USD per gallon."
        >
          <ChartControls
            lines={toLines(products, PRODUCTS)}
            unit={commonUnit(products)}
          />
        </Panel>

        <Panel
          title="Henry Hub front month"
          asOf={pricePublish?.as_of ?? null}
          stale={isStale("yfinance", pricePublish?.as_of)}
          sourceNote="US natural gas, USD per million British thermal units."
        >
          <ChartControls lines={toLines(gas, GAS)} unit={commonUnit(gas)} />
        </Panel>

        <Panel
          title={`Brent forward curve${tradeDate ? ` — ${formatDate(tradeDate)}` : ""}`}
          asOf={curvePublish?.as_of ?? null}
          stale={isStale("curve", curvePublish?.as_of)}
          sourceNote="A single snapshot reconstructed from a Barchart spreads export, not a live board. The as-of stamp is the trade date, so this panel greys until a new export lands."
        >
          {curve.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No curve published.</p>
          ) : (
            <TimeSeriesChart
              lines={[
                {
                  name: "Settle",
                  x: curve.map((c) => c.contract),
                  y: curve.map((c) => c.settle),
                  color: SERIES.navy,
                },
              ]}
              unit="USD/bbl"
              xTickEvery={6}
            />
          )}
        </Panel>

        <Panel
          title="WTI calendar spreads"
          asOf={curvePublish?.as_of ?? null}
          stale={isStale("curve", curvePublish?.as_of)}
          sourceNote="Front minus back, so positive is backwardation. EIA discontinued this route in April 2024 — the series genuinely ends there, which is why this panel reads stale."
        >
          {spreadLines.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No spreads published.</p>
          ) : (
            <ChartControls lines={spreadLines} unit="USD/bbl" />
          )}
        </Panel>
      </main>
    </>
  );
}
