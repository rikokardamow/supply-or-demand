import Link from "next/link";

import type { Headline } from "@/data/queries/overview";
import { formatDate, formatNumber, formatPercent, formatSigned } from "@/lib/format";

/**
 * The headline figures, above everything else.
 *
 * A research page that opens with a chart makes a reader work before it tells them
 * anything. These six numbers are the ones worth knowing before deciding which screen to
 * open, and each is a link to the screen that explains it.
 *
 * Direction is carried by colour *and* by the sign, never colour alone — a red figure
 * with no minus in front of it is unreadable to anyone who cannot separate the two hues,
 * and the sign costs one character.
 */

function decimals(unit: string | null): number {
  // Barrels run to hundreds of thousands, where a decimal is noise; a price or a
  // percentage near 100 needs one, or a real move rounds away to nothing.
  if (unit === "MBBL") return 0;
  if (unit === "rigs") return 0;
  return unit === "%" ? 1 : 2;
}

export function StatStrip({ headlines }: { headlines: Headline[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
        gap: "1px",
        background: "var(--rule)",
        border: "1px solid var(--rule)",
        marginBottom: "var(--space-12)",
      }}
    >
      {headlines.map((h, i) => (
        <Link
          key={h.key}
          href={h.href}
          className="rise stat"
          style={{
            background: "var(--paper)",
            padding: "var(--space-4) var(--space-4) var(--space-3)",
            textDecoration: "none",
            display: "block",
            animationDelay: `${i * 40}ms`,
          }}
        >
          <div
            style={{
              fontSize: "var(--size-micro)",
              letterSpacing: "0.07em",
              textTransform: "uppercase",
              color: "var(--muted)",
              marginBottom: "var(--space-2)",
            }}
          >
            {h.label}
          </div>

          <div
            className="tabular"
            style={{
              fontSize: "1.6rem",
              color: "var(--ink)",
              lineHeight: 1.1,
              letterSpacing: "-0.02em",
            }}
          >
            {formatNumber(h.value, decimals(h.unit))}
          </div>

          <div
            style={{
              fontSize: "var(--size-micro)",
              color: "var(--muted)",
              marginTop: "var(--space-1)",
            }}
          >
            {h.unit ?? ""}
          </div>

          <div
            className="tabular"
            style={{
              fontSize: "var(--size-small)",
              marginTop: "var(--space-3)",
              color:
                h.change === null
                  ? "var(--muted)"
                  : h.change > 0
                    ? "var(--navy)"
                    : h.change < 0
                      ? "var(--red)"
                      : "var(--muted)",
            }}
          >
            {formatSigned(h.change, decimals(h.unit))}
            <span style={{ color: "var(--muted)" }}> latest change</span>
          </div>

          {h.vsMedian !== null ? (
            <div
              className="tabular"
              style={{
                fontSize: "var(--size-small)",
                marginTop: "var(--space-1)",
                color: Math.abs(h.vsMedian) > 10 ? "var(--red)" : "var(--muted)",
              }}
            >
              {formatPercent(h.vsMedian)}
              <span style={{ color: "var(--muted)" }}> vs median</span>
            </div>
          ) : null}

          <div
            style={{
              fontSize: "var(--size-micro)",
              color: "var(--muted)",
              marginTop: "var(--space-2)",
            }}
          >
            {formatDate(h.ts)}
          </div>
        </Link>
      ))}
    </div>
  );
}
