/**
 * The Plotly house style, ported from `core/theme.py`'s "kardamow" template so a chart
 * exported from this app and one exported from the Python side are indistinguishable.
 *
 * Kept in one module rather than repeated per chart: the colours encode meaning (navy is
 * the primary series, orange is always the seasonal median) and a chart that quietly
 * picked its own would break that reading across the site.
 */

export const SERIES = {
  navy: "#0f2a4a",
  lightBlue: "#5b9bd5",
  red: "#c0392b",
  orange: "#e67e22",
  grey: "#95a5a6",
  band: "rgba(150,150,150,0.25)",
} as const;

export const GRID = "#e6e6e6";
export const MUTED = "#757575";

/** Numbers never render in the serif — root CLAUDE.md's chart house style. */
export const BODY_STACK =
  'Inter, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

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
    font: { family: BODY_STACK, size: 12, color: MUTED },
    paper_bgcolor: "white",
    plot_bgcolor: "white",
    margin: { l: 60, r: 24, t: 12, b: 40 },
    hovermode: "x unified",
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.0,
      xanchor: "left",
      x: 0,
    },
    xaxis: { showgrid: false, gridcolor: GRID },
    yaxis: {
      gridcolor: GRID,
      zeroline: false,
      title: unit ? { text: unit, font: { family: BODY_STACK } } : undefined,
    },
  };
}

export const PLOT_CONFIG = { displayModeBar: false, responsive: true } as const;
