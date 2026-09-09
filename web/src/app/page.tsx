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
 * It has one job: say what this is, prove it in a single screen, and get the reader to
 * the section they came for. So it is built the way a product's landing page is built --
 * a claim, the thing itself, then the way in -- rather than as a dashboard index.
 *
 * The claim is stated once, at size. Under it sit the six figures the site exists to
 * publish and one full-width exhibit: a data publication's own product shot is a chart
 * with real numbers in it, not an illustration of one. Everything below that is
 * navigation and provenance.
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

const SCREENS = [
  {
    href: "/balances",
    title: "Balances",
    blurb:
      "The weekly US petroleum picture: the at-a-glance table, and crude, gasoline and distillate stocks against their seasonal ranges.",
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
    href: "/curves",
    title: "Curves",
    blurb:
      "The Brent forward curve and WTI calendar spreads. Both read stale by design — their sources have genuinely stopped.",
  },
  {
    href: "/positioning",
    title: "Positioning",
    blurb:
      "CFTC Commitments of Traders: managed money net length in WTI, Brent, RBOB and heating oil, and what it is as a share of open interest.",
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
 * The series each card draws, and how many decimals its figure wants.
 *
 * Four of the nine screens have a series behind them. Curves, Vessels, Events and
 * Sanctions are curves and registers rather than histories, and a card for one of those
 * shows a count or nothing at all -- drawing a shape for a screen that has no series
 * would be inventing data to fill a slot.
 */
const CARD_SERIES: Record<string, { seriesId: string; digits: number }> = {
  "/balances": { seriesId: "WCESTUS1", digits: 0 },
  "/prices": { seriesId: "fut.lco.f01.close", digits: 2 },
  "/gas": { seriesId: "agsi.EU.full_pct", digits: 1 },
  "/supply": { seriesId: "bh.rigs.united_states.total", digits: 0 },
};

export default async function Home() {
  const [headlines, publishes, lead, leadPublish, cardRows, sanctions] =
    await Promise.all([
      fetchHeadlines(),
      fetchLatestPublishes(),
      fetchSeries(Object.keys(LEAD_SERIES), 5),
      fetchLatestPublishBy("series_long", "yfinance"),
      // One year: a sparkline 220px wide cannot resolve five years of daily closes into
      // anything but a smear, and the card is asking "which way lately", not "what is the
      // history".
      fetchSeries(
        Object.values(CARD_SERIES).map((c) => c.seriesId),
        1,
      ),
      fetchSanctionTotals(),
    ]);

  const grouped = bySeries(cardRows);
  const stats: Record<string, ScreenStat> = {
    "/sanctions": {
      note: `${formatNumber(sanctions.entries, 0)} listed entries · ${formatNumber(
        sanctions.with_imo,
        0,
      )} carry a vessel IMO`,
    },
  };
  for (const [href, card] of Object.entries(CARD_SERIES)) {
    const rows = grouped.get(card.seriesId) ?? [];
    const values = rows
      .map((r) => r.value)
      .filter((v): v is number => v !== null && v !== undefined);
    if (values.length < 2) continue;
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
      <Masthead active="/" full />

      <main>
        {/* Claim on the left, the thing itself on the right. A landing page that states a
            claim across the full width and leaves half the fold empty has spent its best
            space on nothing; a data publication's product shot is a real chart with real
            numbers in it, and putting it here means the claim is answered in the same
            glance it is made. It is interactive for the same reason -- a reader can ask
            their own next question without leaving the front page. */}
        <section
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(min(100%, 30rem), 1fr))",
            alignItems: "center",
            gap: "var(--space-12)",
            padding: "var(--space-12) 0",
          }}
        >
          <div>
            {/* Sized against the window rather than pinned: a headline fixed at 4.4rem is
                a headline that breaks a phone. */}
            <h2
              style={{
                fontFamily: "var(--heading-stack)",
                fontSize: "clamp(2.4rem, 4.6vw, 4rem)",
                lineHeight: 1.02,
                letterSpacing: "-0.03em",
                color: "var(--ink)",
                margin: "0 0 var(--space-6)",
              }}
            >
              Energy fundamentals, counted.
            </h2>
            <p
              style={{
                fontSize: "var(--size-lead)",
                lineHeight: 1.55,
                color: "var(--text)",
                maxWidth: "44ch",
                margin: "0 0 var(--space-6)",
              }}
            >
              Prices, stocks, storage, cargoes and sanctions — pulled from
              primary sources into a local data lake and published here as rows.
              Every figure on this site was computed before it was served; none
              of it is estimated in your browser.
            </p>
            <Link
              href="/balances"
              style={{
                fontSize: "var(--size-small)",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--ink)",
                fontWeight: 600,
                textDecoration: "none",
                borderBottom: "2px solid var(--ink)",
                paddingBottom: "0.2rem",
              }}
            >
              Start with this week&rsquo;s balances →
            </Link>
          </div>

          <div>
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                gap: "var(--space-4)",
                borderBottom: "1px solid var(--rule)",
                paddingBottom: "var(--space-2)",
                marginBottom: "var(--space-4)",
              }}
            >
              <h3 style={{ fontSize: "var(--size-panel)" }}>
                Brent and WTI, front-month close
              </h3>
              <span
                className="tabular"
                style={{
                  fontSize: "var(--size-micro)",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--muted)",
                  whiteSpace: "nowrap",
                }}
              >
                As of {formatDate(leadPublish?.as_of ?? null)}
              </span>
            </div>
            <ChartControls
              lines={toLines(lead, LEAD_SERIES)}
              unit={commonUnit(lead)}
              height={320}
            />
          </div>
        </section>

        <StatStrip headlines={headlines} />

        <section style={{ marginBottom: "var(--space-12)" }}>
          <h3
            style={{
              fontSize: "var(--size-micro)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--muted)",
              fontFamily: "var(--body-stack)",
              fontWeight: 600,
              marginBottom: "var(--space-6)",
            }}
          >
            Nine screens
          </h3>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: "var(--space-8)",
            }}
          >
            {SCREENS.map((screen, i) => (
              <ScreenCard
                key={screen.href}
                href={screen.href}
                title={screen.title}
                blurb={screen.blurb}
                stat={stats[screen.href]}
                delay={120 + i * 40}
              />
            ))}
          </div>
        </section>

        <section>
          <h3
            style={{
              fontSize: "var(--size-panel)",
              marginBottom: "var(--space-2)",
            }}
          >
            What was last published
          </h3>
          <p
            style={{
              fontSize: "var(--size-small)",
              color: "var(--muted)",
              marginBottom: "var(--space-4)",
              maxWidth: "44rem",
            }}
          >
            The as-of column is the data&rsquo;s own date, not the time the
            pipeline ran. A source that has stopped updating shows an old as-of
            however recently it was republished — which is the point of
            recording both.
          </p>
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
                        padding: "var(--space-2) var(--space-3)",
                        borderBottom: "1px solid var(--rule)",
                        fontSize: "var(--size-micro)",
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        color: "var(--muted)",
                        fontWeight: 600,
                        // Three of these four headings are shorter than their column but
                        // "Data as of" wraps onto two lines at some widths, which drags
                        // the whole header row taller for no reason.
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
                      <td style={cell}>{p.table_name}</td>
                      <td
                        style={{
                          ...cell,
                          fontVariantNumeric: "tabular-nums",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {formatDate(p.as_of)}
                      </td>
                      <td
                        style={{
                          ...cell,
                          color: "var(--muted)",
                          fontVariantNumeric: "tabular-nums",
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
          <p
            style={{
              fontSize: "var(--size-micro)",
              color: "var(--muted)",
              marginTop: "var(--space-4)",
            }}
          >
            {formatNumber(publishes.length, 0)} tables published from the lake.
          </p>
        </section>
      </main>
    </>
  );
}

const cell: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--rule-faint)",
  verticalAlign: "top",
};
