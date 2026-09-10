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
 * ground the blend is onto `--surface` (#0a0b0d, rgb(10,11,13)) -- close to black by eye,
 * but not close enough to drop from the arithmetic: `washChroma` composites against the
 * real ground channels below, and chroma turns out NOT to reduce to "the spread times
 * alpha" the way it would against true black. See `washChroma` and the ramp comment
 * below for what it actually takes to balance the two directions here.
 */
const SURPLUS_RGB = "77, 159, 255";
const DEFICIT_RGB = "255, 90, 77";

/**
 * The channels of `--surface` (#0a0b0d), the ground a heat wash actually composites onto.
 * Close to black by eye, but `washChroma`'s arithmetic needs the real values: composited
 * against true (0,0,0) the two wash colours would balance at equal alpha (their raw
 * channel spreads are both 178), but composited against this slightly uneven ground they
 * do not, which is what the retuned ramp below corrects for. Kept as a numeric triple
 * for the same reason as SURPLUS_RGB/DEFICIT_RGB above -- arithmetic, not a `var()`
 * reference -- and drift-guarded against `--surface` itself in HeatTable.test.ts.
 */
export const PANEL_GROUND_RGB = "10, 11, 13";

// The light UI needed a SURPLUS_ALPHA_GAIN here because even after swapping navy for
// light blue the surplus still under-coloured against red on a white ground. There is no
// equivalent single constant here: composited against --surface (not pure black) the two
// colours' chroma-per-unit-alpha is close but not equal, and the gap that matters most is
// the constant offset at low alpha (see the ramp below) -- which a flat gain factor
// cannot correct, so the surplus and deficit ramps are tuned independently instead.

/** The intercept and slope (both signs) of the alpha ramp below. Named, not inlined, so
 * the pair being re-tuned is visible at the definition rather than buried in a ternary. */
const SURPLUS_INTERCEPT = 0.152;
const SURPLUS_SLOPE = 0.352;
const DEFICIT_INTERCEPT = 0.18;
const DEFICIT_SLOPE = 0.34;

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
  // Here the blend is onto --surface, rgb(10,11,13) -- not pure black, and the difference
  // matters: washChroma composites `c*alpha + g*(1-alpha)` per channel against that real
  // ground, not `c*alpha` against (0,0,0). Because the ground channels are uneven (10 <
  // 11 < 13) and the two wash colours sit on opposite sides of that unevenness, the two
  // directions do NOT produce equal chroma at equal alpha, even though their raw channel
  // spreads are both 178. Composited by hand (not by calling washChroma -- see the pinned
  // fixtures in HeatTable.test.ts, which exist precisely so this comment and the function
  // cannot both drift the same way again):
  //   surplus @ threshold (alpha 0.152): R 10+67*.152=20.18, G 11+148*.152=33.50,
  //     B 13+242*.152=49.78 -> chroma 29.60
  //   deficit @ threshold (alpha 0.18):  R 10+245*.18=54.10, G 11+79*.18=25.22,
  //     B 13+64*.18=24.52   -> chroma 29.58
  //   surplus @ cap       (alpha 0.504): R 10+67*.504=43.77, G 11+148*.504=85.59,
  //     B 13+242*.504=134.97 -> chroma 91.20
  //   deficit @ cap       (alpha 0.52):  R 10+245*.52=137.40, G 11+79*.52=52.08,
  //     B 13+64*.52=46.28  -> chroma 91.12
  // Chroma ratio is ~1.001 at both ends (and, because both sides are affine in `scaled`
  // once past the threshold, at every point between). Contrast against the panel ground
  // is NOT held equally tight: it lands within ~1% at the threshold (13.23:1 surplus,
  // 13.06:1 deficit) but the two directions diverge to ~7% at the cap (6.14:1 surplus,
  // 6.59:1 deficit) -- both comfortably clear the 4.5:1 floor, so the trade-off taken was
  // to hold chroma parity exactly across the whole ramp (the property a reader scanning
  // for outliers depends on) rather than squeeze contrast parity tighter at the cap.
  const alpha =
    (pct > 0 ? SURPLUS_INTERCEPT : DEFICIT_INTERCEPT) +
    scaled * (pct > 0 ? SURPLUS_SLOPE : DEFICIT_SLOPE);
  return pct > 0
    ? { rgb: SURPLUS_RGB, alpha }
    : { rgb: DEFICIT_RGB, alpha };
}

/**
 * The channel spread of a wash once blended onto the panel ground -- its perceived
 * colourfulness.
 *
 * **Ground-dependent, and previously wrong against the surface it was actually written
 * for.** The table sits on `--surface` (#0a0b0d, rgb(10,11,13)), not pure black, so the
 * true composite per channel is `c*alpha + g*(1-alpha)` -- not `c*alpha`, which is only
 * the correct blend onto (0,0,0). The two are close enough by eye to look the same
 * screenshot but far enough apart in the arithmetic to mis-balance the ramp below: this
 * function got it wrong for a full task and a review before the true composite was
 * measured. Getting this wrong does not throw -- it returns a plausible number for a
 * colour nobody is looking at, which is the one failure mode a function like this exists
 * to prevent.
 */
export function washChroma(wash: { rgb: string; alpha: number }): number {
  const channels = wash.rgb.split(",").map((n) => Number(n.trim()));
  const ground = PANEL_GROUND_RGB.split(",").map((n) => Number(n.trim()));
  const blended = channels.map(
    (c, i) => c * wash.alpha + ground[i] * (1 - wash.alpha),
  );
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
