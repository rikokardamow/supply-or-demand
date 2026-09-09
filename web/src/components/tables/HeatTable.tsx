import { formatNumber, formatPercent, formatSigned } from "@/lib/format";
import type { WpsrLineRow } from "@/types/database";

/**
 * The WPSR at-a-glance table (Spec 33.02).
 *
 * Reads `serving.wpsr_latest_v` as published — every figure here was computed in Python
 * by `pipelines/eia/wpsr_lines.py`, and nothing is recalculated in the browser (Spec 32
 * §1). `wow` is an absolute change in the line's own unit; `yoy_pct` and `vs_median_pct`
 * are percentages, which is why they are formatted differently.
 *
 * "Heat" is applied only to `vs_median_pct` — distance from the seasonal norm is the
 * column an analyst scans for outliers, and tinting all three would leave nothing
 * standing out. The tint is a background wash rather than coloured text, so the figure
 * itself stays legible at the same contrast as every other number.
 */

/** Beyond this distance from the seasonal median, a cell is worth the eye stopping on. */
const HEAT_THRESHOLD_PCT = 10;
/** Where the wash reaches full strength. Beyond it, saturation stops increasing. */
const HEAT_SATURATION_PCT = 40;

function heatStyle(pct: number | null): { background?: string } {
  if (pct === null || Number.isNaN(pct)) return {};
  const magnitude = Math.abs(pct);
  if (magnitude < HEAT_THRESHOLD_PCT) return {};

  const scaled = Math.min(
    (magnitude - HEAT_THRESHOLD_PCT) / (HEAT_SATURATION_PCT - HEAT_THRESHOLD_PCT),
    1,
  );
  const alpha = 0.08 + scaled * 0.22;
  // Navy for a surplus, red for a deficit -- the house series palette, not a
  // traffic-light scheme: a stock build is not "good" and a draw is not "bad".
  const rgb = pct > 0 ? "15, 42, 74" : "192, 57, 43";
  return { background: `rgba(${rgb}, ${alpha.toFixed(3)})` };
}

/**
 * How many decimals a line's level and week-on-week change deserve.
 *
 * Not a cosmetic choice. Stocks run to hundreds of thousands of barrels, where a decimal
 * is noise; refinery utilisation is a percentage near 98, where rounding to whole units
 * turns a real +0.6 point week into "+1" and a flat week into "0". One rule for both
 * columns would have to be wrong for one of them.
 */
function digitsFor(unit: string | null): number {
  return unit === "%" ? 1 : 0;
}

const cell: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid var(--rule)",
  fontVariantNumeric: "tabular-nums",
  textAlign: "right",
  whiteSpace: "nowrap",
};

const headCell: React.CSSProperties = {
  ...cell,
  textAlign: "right",
  fontWeight: 600,
  fontSize: "0.72rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--muted)",
  borderBottom: "1px solid var(--rule)",
};

export function HeatTable({ rows }: { rows: WpsrLineRow[] }) {
  if (rows.length === 0) {
    return (
      <p style={{ color: "var(--muted)" }}>No WPSR lines published yet.</p>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--body-stack)",
          fontSize: "0.88rem",
        }}
      >
        <thead>
          <tr>
            <th style={{ ...headCell, textAlign: "left" }}>Line</th>
            <th style={{ ...headCell, textAlign: "left" }}>Unit</th>
            <th style={headCell}>Level</th>
            <th style={headCell}>Week</th>
            <th style={headCell}>Year</th>
            <th style={headCell}>vs median</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const digits = digitsFor(row.unit);
            return (
            <tr key={row.line ?? ""}>
              <td style={{ ...cell, textAlign: "left", whiteSpace: "normal" }}>
                {row.label}
              </td>
              <td
                style={{
                  ...cell,
                  textAlign: "left",
                  color: "var(--muted)",
                  fontSize: "0.78rem",
                }}
              >
                {row.unit}
              </td>
              <td style={cell}>{formatNumber(row.value, digits)}</td>
              <td style={cell}>{formatSigned(row.wow, digits)}</td>
              <td style={cell}>{formatPercent(row.yoy_pct)}</td>
              <td style={{ ...cell, ...heatStyle(row.vs_median_pct) }}>
                {formatPercent(row.vs_median_pct)}
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
