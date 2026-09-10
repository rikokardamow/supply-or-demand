import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { baseLayout } from "@/theme/plotly";

/**
 * `plotly.ts` hardcodes "#0a0b0d" and "#2a2f37" rather than referencing --surface and
 * --border, because Plotly needs a real colour string and cannot resolve a CSS custom
 * property. That duplication is unavoidable, but it is only safe while something notices
 * the two copies disagreeing -- retune --surface and every panel moves while the chart
 * ground stays behind, opening a seam inside every `Panel`. This is that guard, in the
 * same style as tokens.pins.test.ts's --navy-rgb derivation: the expectation is read out
 * of tokens.css itself, not restated as a second literal that could drift alongside the
 * first.
 */

const CSS = readFileSync(join(__dirname, "tokens.css"), "utf8");

/** The value of a `--name: value;` declaration in the `:root` block. */
function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(CSS);
  if (!match) throw new Error(`token --${name} is not defined in tokens.css`);
  return match[1].trim();
}

interface AxisLayout {
  linecolor: string;
}

interface ChartLayout {
  paper_bgcolor: string;
  plot_bgcolor: string;
  xaxis: AxisLayout;
  yaxis: AxisLayout;
}

describe("plotly chart ground", () => {
  const layout = baseLayout() as unknown as ChartLayout;

  it("keeps the chart's paper and plot ground identical to --surface", () => {
    expect(layout.paper_bgcolor).toBe(token("surface"));
    expect(layout.plot_bgcolor).toBe(token("surface"));
  });

  it("keeps the axis line colour identical to --border", () => {
    expect(layout.xaxis.linecolor).toBe(token("border"));
    expect(layout.yaxis.linecolor).toBe(token("border"));
  });
});
