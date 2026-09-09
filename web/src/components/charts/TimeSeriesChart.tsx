"use client";

import { useEffect, useRef } from "react";

import { PLOT_CONFIG, SERIES_CYCLE, baseLayout } from "@/theme/plotly";

/**
 * The workhorse: one or more series against time.
 *
 * Plotly is imported inside the effect, not at module scope — it touches `self` when
 * evaluated, which fails Next's prerender even in a client component. See
 * `SeasonalChart` for the full note.
 *
 * Gaps are never bridged (`connectgaps: false`). A series with no observation for a
 * period genuinely has none, and joining across the hole would draw a straight line
 * through missing data as though it were measured.
 */

export type SeriesLine = {
  name: string;
  x: string[];
  y: (number | null)[];
  /** Overrides the palette cycle where a colour carries meaning of its own. */
  color?: string;
  dash?: "solid" | "dot" | "dash";
  /** Plot against a secondary right-hand axis (Spec 33: navy left, light blue right). */
  secondary?: boolean;
};

export function TimeSeriesChart({
  lines,
  unit,
  secondaryUnit,
  height = 320,
  xTickEvery,
}: {
  lines: SeriesLine[];
  unit?: string | null;
  secondaryUnit?: string | null;
  height?: number;
  /**
   * Label only every nth category on a categorical x-axis. A forward curve has ~89
   * contract codes, and Plotly draws every one -- they overlap into an unreadable band.
   * Ignored on a date axis, which thins its own ticks.
   */
  xTickEvery?: number;
}) {
  const node = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!node.current) return;
    const el = node.current;
    let cancelled = false;

    const traces = lines.map((line, i) => ({
      x: line.x,
      y: line.y,
      name: line.name,
      type: "scatter" as const,
      mode: "lines" as const,
      connectgaps: false,
      line: {
        color: line.color ?? SERIES_CYCLE[i % SERIES_CYCLE.length],
        width: i === 0 ? 2 : 1.5,
        dash: line.dash ?? "solid",
      },
      ...(line.secondary ? { yaxis: "y2" } : {}),
    }));

    const layout: Record<string, unknown> = {
      ...baseLayout(unit),
      ...(xTickEvery
        ? { xaxis: { showgrid: false, type: "category", dtick: xTickEvery, tickangle: 0 } }
        : {}),
      ...(secondaryUnit
        ? {
            yaxis2: {
              overlaying: "y",
              side: "right",
              showgrid: false,
              zeroline: false,
              title: { text: secondaryUnit },
            },
            margin: { l: 60, r: 60, t: 12, b: 40 },
          }
        : {}),
    };

    void import("plotly.js-dist-min").then(({ default: Plotly }) => {
      if (cancelled) return;
      void Plotly.newPlot(el, traces, layout, PLOT_CONFIG);
    });

    return () => {
      cancelled = true;
      void import("plotly.js-dist-min").then(({ default: Plotly }) => {
        Plotly.purge(el);
      });
    };
  }, [lines, unit, secondaryUnit, xTickEvery]);

  return <div ref={node} style={{ width: "100%", height }} />;
}
