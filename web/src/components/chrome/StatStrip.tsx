import Link from "next/link";

import { Sparkline } from "@/components/charts/Sparkline";
import { CountUp } from "@/components/chrome/CountUp";
import type { Headline } from "@/data/queries/overview";
import { formatDate, formatPercent, formatSigned } from "@/lib/format";

/**
 * The headline figures, as a monitor row of terminal cells.
 *
 * Each cell is bordered because each is a destination: label, level, direction, a year of
 * shape, and the date the figure is for. An earlier version set these as bare numbers
 * separated by whitespace, on the reasoning that a border was doing work whitespace could
 * do. It could not: without an edge, six figures in a row read as one undifferentiated band
 * and nothing said any of them was clickable.
 *
 * Direction is carried by sign *and* colour, never colour alone -- a red figure with no
 * minus in front of it is unreadable to anyone who cannot separate the two hues, and the
 * sign costs one character.
 */

function decimals(unit: string | null): number {
  // Barrels and rigs run to hundreds or thousands, where a decimal is noise; a price or a
  // percentage needs one, or a real move rounds away to nothing.
  if (unit === "MBBL" || unit === "rigs") return 0;
  return unit === "%" ? 1 : 2;
}

function toneFor(value: number | null): string {
  if (value === null || value === 0) return "var(--muted)";
  return value > 0 ? "var(--up)" : "var(--down)";
}

function toneSoft(value: number | null): string {
  if (value === null || value === 0) return "var(--surface-2)";
  return value > 0 ? "var(--up-soft)" : "var(--down-soft)";
}

export function StatStrip({
  headlines,
  sparks = {},
}: {
  headlines: Headline[];
  /** A year of shape per headline key, where the series is cheap enough to have fetched. */
  sparks?: Record<string, number[]>;
}) {
  return (
    <div
      className="term-grid"
      style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(128px, 1fr))",
        marginBottom: "var(--space-8)",
      }}
    >
      {headlines.map((h) => {
        const spark = sparks[h.key];
        return (
          <Link key={h.key} href={h.href} className="term-cell">
            <div className="k">{h.label}</div>

            <div className="v tabular" style={{ display: "flex", alignItems: "baseline", gap: "0.35rem" }}>
              <CountUp value={h.value} digits={decimals(h.unit)} />
              <span
                style={{ fontSize: "var(--size-micro)", color: "var(--faint)" }}
              >
                {h.unit ?? ""}
              </span>
            </div>

            {spark && spark.length > 1 ? (
              <div style={{ marginBottom: "var(--space-3)" }}>
                <Sparkline
                  values={spark}
                  color={
                    h.change !== null && h.change < 0
                      ? "var(--down)"
                      : "var(--up)"
                  }
                  label={`${h.label}: the last year`}
                  height={28}
                />
              </div>
            ) : null}

            <div
              className="d"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.35rem",
                flexWrap: "wrap",
              }}
            >
              <span
                className="tabular"
                style={{
                  fontWeight: 600,
                  color: toneFor(h.change),
                  background: toneSoft(h.change),
                  padding: "0.1rem 0.4rem",
                  borderRadius: "var(--r-sm)",
                }}
              >
                {formatSigned(h.change, decimals(h.unit))}
              </span>
              {h.vsMedian !== null ? (
                <span
                  className="tabular"
                  style={{
                    color: "var(--muted)",
                  }}
                >
                  {formatPercent(h.vsMedian)} vs median
                </span>
              ) : null}
            </div>

            <div
              style={{
                fontSize: "var(--size-micro)",
                color: "var(--faint)",
                marginTop: "var(--space-2)",
              }}
            >
              {formatDate(h.ts)}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
