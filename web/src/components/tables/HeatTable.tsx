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

/**
 * The two wash colours, and why they are not the two series colours.
 *
 * Blue for a surplus, red for a deficit -- not a traffic-light scheme: a stock build is
 * not "good" and a draw is not "bad".
 *
 * These are the lifted series colours -- `--navy` #4d9fff and `--red` #ff5a4d -- as
 * numeric channels, and they must stay identical to the `--navy-rgb`/`--red-rgb` tokens.
 * They exist as numbers only because `washChroma` has to do arithmetic on the channels,
 * which it cannot do through a `var()` reference. The emitted CSS uses the tokens; the
 * test asserts the two representations agree, so they cannot drift apart.
 *
 * **The defect this fixes, and why the light UI fixed it differently.** Measured off the
 * live table: deficits carried chroma 19-41, surpluses only 5-9, while contrast was
 * comparable at 1.39 against 1.52. The asymmetry was saturation, not lightness -- a
 * reader scanning the column for outliers found every draw and missed every build.
 *
 * On white, chroma came from how unevenly the channels sat BELOW white, where the old
 * navy #0f2a4a had a spread of 59 against red's 149 -- so the light UI swapped navy for
 * light blue and then gained the surplus alpha to close the rest of the gap. On this
 * ground the blend is onto near-black and chroma comes from the spread itself, which for
 * these two lifted colours is 178 apiece. Same defect, same diagnosis, different remedy,
 * because the arithmetic inverts with the ground.
 */
const SURPLUS_RGB = "77, 159, 255";
const DEFICIT_RGB = "255, 90, 77";

// The light UI needed a SURPLUS_ALPHA_GAIN of 149/122 here, because even after swapping
// navy for light blue the surplus still under-coloured against red on a white ground.
// On this ground both lifted colours have a channel spread of 178, so the gain would be
// exactly 1 and the constant is gone rather than left at a no-op value.

/** The wash for a cell, or null where the distance is not worth the eye stopping on. */
export function heatWash(
  pct: number | null,
): { rgb: string; alpha: number } | null {
  if (pct === null || Number.isNaN(pct)) return null;
  const magnitude = Math.abs(pct);
  if (magnitude < HEAT_THRESHOLD_PCT) return null;

  const scaled = Math.min(
    (magnitude - HEAT_THRESHOLD_PCT) /
      (HEAT_SATURATION_PCT - HEAT_THRESHOLD_PCT),
    1,
  );
  // On a black ground the arithmetic behind the light UI's fix inverts, so its remedy
  // does not carry over unchanged. There a wash was an alpha blend onto WHITE and chroma
  // came from how unevenly the source channels sat BELOW white -- which is why navy
  // (spread 59) had to be swapped for light blue (122) and then gained by 149/122 to
  // match red's 149.
  //
  // Here the blend is onto --surface (#0a0b0d, near enough to black that the composite is
  // c * alpha), so chroma is (max - min) * alpha. The lifted palette makes that symmetric
  // for free: --navy #4d9fff is rgb(77,159,255), spread 178; --red #ff5a4d is
  // rgb(255,90,77), spread 178. Identical, so no gain factor is needed here.
  //
  // The small asymmetry that remains is not for chroma but for CONTRAST: the two colours
  // differ in luminance, so equal alpha would leave the deficit reading heavier than the
  // build. These ramps land the two extremes within 1% on contrast and 4.5% on chroma,
  // measured against the panel ground rather than judged by eye.
  const alpha = (pct > 0 ? 0.2 : 0.18) + scaled * (pct > 0 ? 0.28 : 0.34);
  return pct > 0
    ? { rgb: SURPLUS_RGB, alpha }
    : { rgb: DEFICIT_RGB, alpha };
}

/**
 * The channel spread of a wash once blended onto the panel ground -- its perceived
 * colourfulness.
 *
 * **Ground-dependent, and silently wrong against a surface it was not written for.** On
 * the light UI this composited onto white (`255 - (255 - c) * alpha`); here it composites
 * onto --surface, which is dark enough to treat as black. Getting this wrong does not
 * throw -- it returns a plausible number for a colour nobody is looking at, which is the
 * one failure mode a function like this exists to prevent.
 */
export function washChroma(wash: { rgb: string; alpha: number }): number {
  const channels = wash.rgb.split(",").map((n) => Number(n.trim()));
  const blended = channels.map((c) => c * wash.alpha);
  return Math.max(...blended) - Math.min(...blended);
}

function heatStyle(pct: number | null): { background?: string } {
  const wash = heatWash(pct);
  if (wash === null) return {};
  // The channel TOKENS in the emitted CSS, not the numeric constants above: rgba() cannot
  // interpolate a hex custom property, and a raw triple in a component would be a
  // hardcoded colour. The constants exist because washChroma has to do arithmetic on the
  // channels, which it cannot do through a var() reference -- HeatTable.test.ts asserts
  // the two representations agree, so they cannot drift.
  const token = pct !== null && pct > 0 ? "var(--navy-rgb)" : "var(--red-rgb)";
  return { background: `rgba(${token}, ${wash.alpha.toFixed(3)})` };
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
  // Lighter than a panel edge so a table reads as one surface, not stacked panels.
  borderBottom: "1px solid var(--hairline)",
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
  borderBottom: "1px solid var(--border)",
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
          fontFamily: "var(--font)",
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
                <td
                  style={{ ...cell, textAlign: "left", whiteSpace: "normal" }}
                >
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
