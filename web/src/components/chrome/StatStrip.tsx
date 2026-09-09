import Link from "next/link";

import { CountUp } from "@/components/chrome/CountUp";
import type { Headline } from "@/data/queries/overview";
import { formatDate, formatPercent, formatSigned } from "@/lib/format";

/**
 * The headline figures, above everything else.
 *
 * A research page that opens with a chart makes a reader work before it tells them
 * anything. These six numbers are worth knowing before choosing a screen, and each links
 * to the one that explains it.
 *
 * No boxes. An earlier version drew a bordered grid, which read as dashboard widgets
 * rather than as a masthead of figures — the border was doing work that whitespace and a
 * single hairline do better. Labels are stated once in the row, not repeated per tile:
 * six copies of "latest change" is noise a reader has to look past to reach the numbers.
 *
 * Direction is carried by sign *and* colour, never colour alone — a red figure with no
 * minus in front of it is unreadable to anyone who cannot separate the two hues, and the
 * sign costs one character.
 */

function decimals(unit: string | null): number {
  // Barrels and rigs run to hundreds or thousands, where a decimal is noise; a price or
  // a percentage needs one, or a real move rounds away to nothing.
  if (unit === "MBBL" || unit === "rigs") return 0;
  return unit === "%" ? 1 : 2;
}

function toneFor(value: number | null): string {
  if (value === null || value === 0) return "var(--muted)";
  return value > 0 ? "var(--navy)" : "var(--red)";
}

export function StatStrip({ headlines }: { headlines: Headline[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: "var(--space-8) var(--space-6)",
        borderTop: "1px solid var(--rule)",
        borderBottom: "1px solid var(--rule)",
        padding: "var(--space-6) 0",
        marginBottom: "var(--space-12)",
      }}
    >
      {headlines.map((h, i) => (
        <Link
          key={h.key}
          href={h.href}
          className="rise stat"
          style={{
            textDecoration: "none",
            display: "block",
            animationDelay: `${i * 40}ms`,
          }}
        >
          <div
            className="stat-label"
            style={{
              fontSize: "var(--size-micro)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--muted)",
              marginBottom: "var(--space-3)",
            }}
          >
            {h.label}
          </div>

          {/* Unit sits on the baseline beside the figure rather than under it: a third
              line per tile costs six lines of vertical noise across the row. */}
          <div
            style={{ display: "flex", alignItems: "baseline", gap: "0.3rem" }}
          >
            <span
              className="tabular"
              style={{
                fontSize: "2.1rem",
                color: "var(--ink)",
                lineHeight: 1,
                letterSpacing: "-0.03em",
                fontWeight: 500,
              }}
            >
              <CountUp value={h.value} digits={decimals(h.unit)} />
            </span>
            <span
              style={{ fontSize: "var(--size-micro)", color: "var(--muted)" }}
            >
              {h.unit ?? ""}
            </span>
          </div>

          <div
            className="tabular"
            style={{
              fontSize: "var(--size-small)",
              marginTop: "var(--space-3)",
              color: toneFor(h.change),
              display: "flex",
              gap: "0.6rem",
            }}
          >
            <span>{formatSigned(h.change, decimals(h.unit))}</span>
            {h.vsMedian !== null ? (
              <span style={{ color: toneFor(h.vsMedian) }}>
                {formatPercent(h.vsMedian)}
                <span style={{ color: "var(--muted)" }}> med</span>
              </span>
            ) : null}
          </div>

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
