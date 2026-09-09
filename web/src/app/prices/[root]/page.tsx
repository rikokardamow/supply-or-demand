import { notFound } from "next/navigation";
import Link from "next/link";

import {
  MA_WINDOWS,
  TickerPanels,
  maSeriesId,
} from "@/components/charts/TickerPanels";
import { PageHeader } from "@/components/chrome/PageHeader";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeasonalBand } from "@/data/queries/seasonal";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";

/**
 * One screen per ticker (Spec 33: prices). Each shows the close against its 50/100/200
 * session moving averages, and the close against its own seasonal range.
 *
 * A dynamic segment rather than five near-identical pages: the panels differ only by
 * root, label and unit, and copying them would guarantee they drift apart.
 */
export const revalidate = 3600;

const TICKERS = [
  { root: "cl", label: "WTI crude", unit: "USD/bbl" },
  { root: "lco", label: "Brent crude", unit: "USD/bbl" },
  { root: "ng", label: "Henry Hub gas", unit: "USD/MMBtu" },
  { root: "ho", label: "Heating oil", unit: "USD/gal" },
  { root: "rb", label: "RBOB gasoline", unit: "USD/gal" },
] as const;

export function generateStaticParams() {
  return TICKERS.map((t) => ({ root: t.root }));
}

export default async function TickerPage({
  params,
}: {
  params: Promise<{ root: string }>;
}) {
  const { root } = await params;
  const ticker = TICKERS.find((t) => t.root === root);
  // An unknown root is a 404, not an empty chart: a page that renders chrome around
  // nothing looks like the data is missing rather than the URL being wrong.
  if (!ticker) notFound();

  const seriesIds = [
    `fut.${ticker.root}.f01.close`,
    ...MA_WINDOWS.map((w) => maSeriesId(ticker.root, w)),
  ];

  const [price, band, publish] = await Promise.all([
    fetchSeries(seriesIds, 5),
    fetchSeasonalBand(`fut.${ticker.root}.f01.close`),
    fetchLatestPublishBy("series_long", "yfinance"),
  ]);

  return (
    <>
      <PageHeader
        active="/prices"
        title="Prices"
        dek="Front-month closes against their moving averages and seasonal ranges"
      />

      <main>
        <nav
          aria-label="Tickers"
          style={{ display: "flex", gap: "1.1rem", margin: "0 0 1.5rem" }}
        >
          {TICKERS.map((t) => (
            <Link
              key={t.root}
              href={`/prices/${t.root}`}
              aria-current={t.root === ticker.root ? "page" : undefined}
              style={{
                fontSize: "0.85rem",
                textDecoration: "none",
                color: t.root === ticker.root ? "var(--ink)" : "var(--muted)",
                fontWeight: t.root === ticker.root ? 600 : 400,
                borderBottom:
                  t.root === ticker.root
                    ? "2px solid var(--ink)"
                    : "2px solid transparent",
                paddingBottom: "0.1rem",
              }}
            >
              {t.label}
            </Link>
          ))}
        </nav>

        <TickerPanels
          root={ticker.root}
          label={ticker.label}
          unit={ticker.unit}
          price={price}
          band={band}
          asOf={publish?.as_of ?? null}
          stale={isStale("yfinance", publish?.as_of)}
        />
      </main>
    </>
  );
}
