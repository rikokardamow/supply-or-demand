/**
 * A one-line trace, small enough to sit inside a card.
 *
 * Hand-drawn SVG rather than Plotly. Eight of these on the front page would mean eight
 * Plotly instances for eight lines that carry no axes, no legend, no hover and no zoom --
 * a megabyte of chart library to draw what a `<path>` draws exactly. It also renders on
 * the server, so the cards arrive with their shapes already in the HTML.
 *
 * **No axis, so no scale.** A sparkline says shape and direction, never level; the card
 * states the level in figures beside it. The line is drawn against its own min and max,
 * which is what makes the shape readable and also what stops the reader inferring
 * anything quantitative from the height.
 */

const WIDTH = 220;
const HEIGHT = 40;
const PAD = 2;

export function Sparkline({
  values,
  color = "var(--navy)",
  label,
}: {
  values: number[];
  color?: string;
  /** Read out to a screen reader in place of the drawing. */
  label: string;
}) {
  // Two points is the fewest that can make a line. One value, or a flat series where
  // max === min, would divide by zero below.
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;

  const points = values.map((value, i) => {
    const x = PAD + (i / (values.length - 1)) * (WIDTH - PAD * 2);
    // A genuinely flat series draws down the middle rather than at the top or bottom,
    // where an unchanged line would read as if it were pinned to an extreme.
    const t = span === 0 ? 0.5 : (value - min) / span;
    const y = HEIGHT - PAD - t * (HEIGHT - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
      height={HEIGHT}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      style={{ display: "block", overflow: "visible" }}
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      {/* The last point, marked. On a line with no axis it is the only way to tell which
          end is now. */}
      <circle
        cx={points[points.length - 1].split(",")[0]}
        cy={points[points.length - 1].split(",")[1]}
        r={2}
        fill={color}
      />
    </svg>
  );
}
