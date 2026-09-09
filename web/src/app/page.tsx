import Link from "next/link";

import { ChartControls } from "@/components/charts/ChartControls";
import { Masthead } from "@/components/chrome/Masthead";
import { ScreenCard, type ScreenStat } from "@/components/chrome/ScreenCard";
import { StatStrip } from "@/components/chrome/StatStrip";
import { fetchSanctionTotals } from "@/data/queries/events";
import { fetchHeadlines } from "@/data/queries/overview";
import {
  fetchLatestPublishBy,
  fetchLatestPublishes,
} from "@/data/queries/publishLog";
import { bySeries, fetchSeries } from "@/data/queries/series";
import { commonUnit, toLines } from "@/data/toLines";
import { formatDate, formatNumber } from "@/lib/format";

/**
 * The front page.
 *
 * It has one job: say what this is, prove it in a single screen, and get the reader to the
 * section they came for. So it is built the way a product's landing page is built -- a
 * claim, the thing itself, then the way in.
 *
 * The provenance table at the foot is not filler. It is the site's honesty page -- every
 * table, the data's own as-of, and when the pipeline last ran -- and putting it on the
 * front page rather than behind an "About" link is the point.
 */
export const revalidate = 3600;

const LEAD_SERIES = {
  "fut.lco.f01.close": "Brent",
  "fut.cl.f01.close": "WTI",
};

/** The series behind each headline card's sparkline, keyed by `Headline.key`. */
const HEADLINE_SPARKS: Record<string, string> = {
  wti: "fut.cl.f01.close",
  brent: "fut.lco.f01.close",
  gas: "fut.ng.f01.close",
  eu_storage: "agsi.EU.full_pct",
  us_crude: "WCESTUS1",
  rigs: "bh.rigs.united_states.total",
};

const SCREENS = [
  {
    href: "/balances",
    title: "Balances",
    blurb:
      "The weekly US petroleum picture: the at-a-glance table, and crude, gasoline and distillate stocks against their seasonal ranges.",
  },
  {
    href: "/oil-math",
    title: "Oil math",
    blurb:
      "The weekly US crude balance and where it fails to close, days of cover, refinery utilisation against runs, and the 3-2-1 margin.",
  },
  {
    href: "/prices",
    title: "Prices",
    blurb:
      "Front-month closes for crude, products and gas, each against its 50, 100 and 200-session moving averages and its own seasonal range.",
  },
  {
    href: "/gas",
    title: "Gas",
    blurb:
      "European storage against its seasonal band, fullness by country, injection and withdrawal, and LNG send-out against terminal inventory.",
  },
  {
    href: "/supply",
    title: "Supply",
    blurb:
      "Drilling activity, US monthly production and crude acquisition cost, the OPEC balance and JODI closing stocks.",
  },
  {
    href: "/flows",
    title: "Flows",
    blurb:
      "EIA inter-PADD crude movements by pipeline, rail and tanker — including the Midwest-to-Gulf reversal that shale built.",
  },
  {
    href: "/curves",
    title: "Curves",
    blurb:
      "The Brent forward curve and WTI calendar spreads. Both read stale by design — their sources have genuinely stopped.",
  },
  {
    href: "/positioning",
    title: "Positioning",
    blurb:
      "CFTC Commitments of Traders: managed money long and short against open interest, and net length as a share of it.",
  },
  {
    href: "/vessels",
    title: "Vessels",
    blurb:
      "Live AIS positions in the chokepoints and anchorages, coloured by reported class. A terrestrial network, so empty ocean means no receiver.",
  },
  {
    href: "/events",
    title: "Events",
    blurb:
      "Tagged news, OFAC listings and self-hosted social sentiment, with the coverage each source actually provides.",
  },
  {
    href: "/sanctions",
    title: "Sanctions",
    blurb:
      "The OFAC SDN list and the ships on it — a register of listed vessels by IMO, flag and owner, never a position.",
  },
];

/**
 * The series each screen card draws, and how many decimals its figure wants.
 *
 * Six of the eleven screens have a series behind them. Curves, Vessels, Events and
 * Sanctions are curves and registers rather than histories, and a card for one of those
 * shows a count or nothing at all -- drawing a shape for a screen that has no series would
 * be inventing data to fill a slot.
 */
const CARD_SERIES: Record<string, { seriesId: string; digits: number }> = {
  "/balances": { seriesId: "WCESTUS1", digits: 0 },
  "/prices": { seriesId: "fut.lco.f01.close", digits: 2 },
  "/gas": { seriesId: "agsi.EU.full_pct", digits: 1 },
  "/supply": { seriesId: "bh.rigs.united_states.total", digits: 0 },
  "/positioning": { seriesId: "cftc.cl.oi", digits: 0 },
  "/oil-math": { seriesId: "WPULEUS3", digits: 1 },
};

export default async function Home() {
  const sparkIds = [
    ...new Set([
      ...Object.values(HEADLINE_SPARKS),
      ...Object.values(CARD_SERIES).map((c) => c.seriesId),
    ]),
  ];

  const [headlines, publishes, lead, leadPublish, sparkRows, sanctions] =
    await Promise.all([
      fetchHeadlines(),
      fetchLatestPublishes(),
      fetchSeries(Object.keys(LEAD_SERIES), 5),
      fetchLatestPublishBy("series_long", "yfinance"),
      // One year: a sparkline a couple of hundred pixels wide cannot resolve five years of
      // daily closes into anything but a smear, and the card is asking "which way lately",
      // not "what is the history".
      fetchSeries(sparkIds, 1),
      fetchSanctionTotals(),
    ]);

  const grouped = bySeries(sparkRows);
  const valuesFor = (seriesId: string) =>
    (grouped.get(seriesId) ?? [])
      .map((r) => r.value)
      .filter((v): v is number => v !== null && v !== undefined);

  const sparks: Record<string, number[]> = {};
  for (const [key, seriesId] of Object.entries(HEADLINE_SPARKS)) {
    const values = valuesFor(seriesId);
    if (values.length > 1) sparks[key] = values;
  }

  const stats: Record<string, ScreenStat> = {
    "/sanctions": {
      note: `${formatNumber(sanctions.entries, 0)} listed entries · ${formatNumber(
        sanctions.with_imo,
        0,
      )} carry a vessel IMO`,
    },
  };
  for (const [href, card] of Object.entries(CARD_SERIES)) {
    const values = valuesFor(card.seriesId);
    if (values.length < 2) continue;
    const rows = grouped.get(card.seriesId) ?? [];
    stats[href] = {
      spark: values,
      value: values[values.length - 1],
      change: values[values.length - 1] - values[values.length - 2],
      unit: rows[rows.length - 1]?.unit ?? null,
      digits: card.digits,
    };
  }

  return (
    <>
      <Masthead active="/" />

      <main>
        <section
          style={{
            padding: "var(--space-12) 0 var(--space-8)",
            maxWidth: "52rem",
          }}
        >
          <span
            style={{
              display: "inline-block",
              fontSize: "var(--size-micro)",
              fontWeight: 600,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              color: "var(--accent)",
              background: "var(--accent-soft)",
              padding: "0.25rem 0.6rem",
              borderRadius: "var(--r-pill)",
              marginBottom: "var(--space-5)",
            }}
          >
            {formatNumber(publishes.length, 0)} datasets · primary sources only
          </span>

          <h2
            style={{
              fontSize: "var(--size-display)",
              lineHeight: 1.05,
              letterSpacing: "-0.035em",
              fontWeight: 700,
              marginBottom: "var(--space-5)",
            }}
          >
            Energy fundamentals, counted.
          </h2>

          <p
            style={{
              fontSize: "var(--size-lead)",
              lineHeight: 1.6,
              color: "var(--muted)",
              maxWidth: "46ch",
              marginBottom: "var(--space-6)",
            }}
          >
            Prices, stocks, storage, cargo movements, positioning and sanctions,
            assembled from primary sources and published as figures you can
            interrogate. Every number is computed before the page is served, so
            what you read is what was measured &mdash; never an estimate made in
            your browser.
          </p>

          <p
            style={{
              fontSize: "var(--size-body)",
              color: "var(--faint)",
              maxWidth: "46ch",
              marginBottom: "var(--space-6)",
            }}
          >
            The working evidence behind Kardamow &mdash; independent research on
            energy, macro and geopolitics.
          </p>

          <div
            style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}
          >
            <Link
              href="/balances"
              style={{
                background: "var(--accent)",
                color: "#fff",
                fontSize: "var(--size-small)",
                fontWeight: 600,
                padding: "0.55rem 1.1rem",
                borderRadius: "var(--r-md)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              This week&rsquo;s balances
            </Link>
            <Link
              href="/positioning"
              className="card card-link"
              style={{
                fontSize: "var(--size-small)",
                fontWeight: 600,
                padding: "0.55rem 1.1rem",
                borderRadius: "var(--r-md)",
              }}
            >
              Positioning
            </Link>
          </div>
        </section>

        <StatStrip headlines={headlines} sparks={sparks} />

        {/* The exhibit. A data publication's product shot is a real chart with real numbers
            in it, and it is interactive here for the same reason: a reader can answer their
            own next question without leaving the front page. */}
        <section className="card" style={{ marginBottom: "var(--space-8)" }}>
          <header
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: "var(--space-4)",
              padding: "var(--space-4) var(--space-5)",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <h3 style={{ fontSize: "var(--size-panel)" }}>
              Brent and WTI, front-month close
            </h3>
            <span
              className="tabular"
              style={{
                fontSize: "var(--size-micro)",
                color: "var(--muted)",
                whiteSpace: "nowrap",
              }}
            >
              As of {formatDate(leadPublish?.as_of ?? null)}
            </span>
          </header>
          <div style={{ padding: "var(--space-5)" }}>
            <ChartControls
              lines={toLines(lead, LEAD_SERIES)}
              unit={commonUnit(lead)}
              height={340}
            />
          </div>
        </section>

        <section style={{ marginBottom: "var(--space-8)" }}>
          <h3
            style={{
              fontSize: "var(--size-micro)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--muted)",
              fontWeight: 600,
              marginBottom: "var(--space-4)",
            }}
          >
            The screens
          </h3>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "var(--space-4)",
            }}
          >
            {SCREENS.map((screen, i) => (
              <ScreenCard
                key={screen.href}
                href={screen.href}
                title={screen.title}
                blurb={screen.blurb}
                stat={stats[screen.href]}
                delay={120 + i * 30}
              />
            ))}
          </div>
        </section>

        <section className="card">
          <header
            style={{
              padding: "var(--space-4) var(--space-5)",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <h3
              style={{
                fontSize: "var(--size-panel)",
                marginBottom: "var(--space-1)",
              }}
            >
              What was last published
            </h3>
            <p
              style={{
                fontSize: "var(--size-small)",
                color: "var(--muted)",
                maxWidth: "62ch",
              }}
            >
              &ldquo;Data as of&rdquo; is the date the figures describe, not the
              time the job ran. A source that has stopped updating keeps its old
              as-of however recently it was refreshed &mdash; which is exactly
              why both are recorded.
            </p>
          </header>
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "var(--size-small)",
              }}
            >
              <thead>
                <tr>
                  {["Table", "Data as of", "Published", "Note"].map((h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "var(--space-3) var(--space-5)",
                        borderBottom: "1px solid var(--border)",
                        fontSize: "var(--size-micro)",
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                        color: "var(--muted)",
                        fontWeight: 600,
                        // Three of these four headings are shorter than their column but
                        // "Data as of" wraps onto two lines at some widths, which drags the
                        // whole header row taller for no reason.
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {publishes
                  .slice()
                  .sort((a, b) =>
                    (a.table_name ?? "").localeCompare(b.table_name ?? ""),
                  )
                  .map((p) => (
                    <tr key={p.table_name ?? ""}>
                      <td style={{ ...cell, fontWeight: 500 }}>
                        {p.table_name}
                      </td>
                      <td
                        className="tabular"
                        style={{ ...cell, whiteSpace: "nowrap" }}
                      >
                        {formatDate(p.as_of)}
                      </td>
                      <td
                        className="tabular"
                        style={{
                          ...cell,
                          color: "var(--muted)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {formatDate(p.published_at)}
                      </td>
                      <td style={{ ...cell, color: "var(--muted)" }}>
                        {p.source_note}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  );
}

const cell: React.CSSProperties = {
  padding: "var(--space-3) var(--space-5)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
};
