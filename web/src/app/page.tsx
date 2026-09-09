import Link from "next/link";

import { Masthead } from "@/components/chrome/Masthead";
import { StatStrip } from "@/components/chrome/StatStrip";
import { fetchHeadlines } from "@/data/queries/overview";
import { fetchLatestPublishes } from "@/data/queries/publishLog";
import { formatDate, formatNumber } from "@/lib/format";

/**
 * The front page: the numbers first, then a way in.
 *
 * A research site that opens on a chart makes a reader work before it has told them
 * anything. This opens with the six figures worth knowing, each linking to the screen
 * that explains it, and closes with what the pipelines last published — which doubles as
 * the site's own honesty page: every source, when it last delivered, and how much.
 */
export const revalidate = 3600;

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

export default async function Home() {
  const [headlines, publishes] = await Promise.all([
    fetchHeadlines(),
    fetchLatestPublishes(),
  ]);

  return (
    <main>
      <Masthead active="/" />

      <p
        style={{
          textAlign: "center",
          color: "var(--muted)",
          fontSize: "var(--size-small)",
          maxWidth: "34rem",
          margin: "0 auto var(--space-8)",
        }}
      >
        Energy and macro research. Every figure is computed from a local data lake and
        published as rows — nothing on this site is calculated in your browser.
      </p>

      <StatStrip headlines={headlines} />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "var(--space-8) var(--space-8)",
          marginBottom: "var(--space-12)",
        }}
      >
        {SCREENS.map((screen, i) => (
          <Link
            key={screen.href}
            href={screen.href}
            className="rise screen-card"
            style={{
              textDecoration: "none",
              display: "block",
              paddingTop: "var(--space-3)",
              borderTop: "1px solid var(--rule)",
              animationDelay: `${120 + i * 40}ms`,
            }}
          >
            <h3
              style={{
                fontSize: "var(--size-lead)",
                marginBottom: "var(--space-2)",
                color: "var(--ink)",
              }}
            >
              {screen.title}
            </h3>
            <p style={{ fontSize: "var(--size-small)", color: "var(--muted)" }}>
              {screen.blurb}
            </p>
          </Link>
        ))}
      </div>

      <section>
        <h2
          style={{
            fontSize: "var(--size-panel)",
            marginBottom: "var(--space-2)",
          }}
        >
          What was last published
        </h2>
        <p
          style={{
            fontSize: "var(--size-small)",
            color: "var(--muted)",
            marginBottom: "var(--space-4)",
            maxWidth: "44rem",
          }}
        >
          The as-of column is the data&rsquo;s own date, not the time the pipeline ran. A
          source that has stopped updating shows an old as-of however recently it was
          republished — which is the point of recording both.
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
                .sort((a, b) => (a.table_name ?? "").localeCompare(b.table_name ?? ""))
                .map((p) => (
                  <tr key={p.table_name ?? ""}>
                    <td style={cell}>{p.table_name}</td>
                    <td style={{ ...cell, fontVariantNumeric: "tabular-nums" }}>
                      {formatDate(p.as_of)}
                    </td>
                    <td
                      style={{
                        ...cell,
                        color: "var(--muted)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {formatDate(p.published_at)}
                    </td>
                    <td style={{ ...cell, color: "var(--muted)" }}>{p.source_note}</td>
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
  );
}

const cell: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--rule-faint)",
  verticalAlign: "top",
};
