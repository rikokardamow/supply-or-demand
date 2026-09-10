/**
 * The Plotly house style for a black ground.
 *
 * **This no longer matches `core/theme.py` value-for-value, deliberately.** It matches it
 * *role*-for-role: navy is still the primary series, orange is still always the seasonal
 * median, and the cycle order is unchanged. But navy at #0f2a4a is invisible on black, so
 * every series is re-derived at a luminance that survives the terminal ground. A chart
 * here and the same chart exported from Python therefore read the same and are not the
 * same colour. That is the trade the terminal restyle made; see
 * specs/33_frontend-nextjs.md.
 */

export const SERIES = {
  navy: "#4d9fff",
  lightBlue: "#9fd8ff",
  red: "#ff5a4d",
  orange: "#ffa62b",
  grey: "#99a3ad",
  band: "rgba(160,170,185,0.18)",
} as const;

export const GRID = "#1e232b";
export const MUTED = "#9aa2ad";

/** Every figure and axis tick is monospace, matching the chrome. */
export const BODY_STACK =
  '"JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/**
 * The order additional series take when a chart draws several at once. Navy first
 * because it reads as the primary; grey last because it recedes.
 */
export const SERIES_CYCLE = [
  SERIES.navy,
  SERIES.lightBlue,
  SERIES.orange,
  SERIES.red,
  SERIES.grey,
] as const;

/**
 * Layout every chart starts from. No title: `Panel` owns the heading, so a chart that
 * painted its own would produce two.
 */
export function baseLayout(unit?: string | null): Record<string, unknown> {
  return {
    font: { family: BODY_STACK, size: 10, color: MUTED },
    paper_bgcolor: "#0a0b0d",
    plot_bgcolor: "#0a0b0d",
    margin: { l: 46, r: 12, t: 8, b: 28 },
    hovermode: "x unified",
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.0,
      xanchor: "left",
      x: 0,
    },
    xaxis: { showgrid: false, gridcolor: GRID, linecolor: "#2a2f37", zeroline: false },
    yaxis: {
      gridcolor: GRID,
      zeroline: false,
      linecolor: "#2a2f37",
      title: unit ? { text: unit, font: { family: BODY_STACK } } : undefined,
    },
  };
}

export const PLOT_CONFIG = { displayModeBar: false, responsive: true } as const;
