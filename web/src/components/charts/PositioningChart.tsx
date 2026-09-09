"use client";

import { useEffect, useRef } from "react";

import { PLOT_CONFIG, SERIES, baseLayout } from "@/theme/plotly";

/**
 * One contract's managed money book: the two gross legs as bars, open interest as a line.
 *
 * Bars because long and short are **stocks measured on one date**, not a continuous
 * quantity — the CFTC counts the book every Tuesday and there is nothing in between, so a
 * line joining the counts draws a path the position never took. Fifty-two discrete
 * readings a year is exactly what a bar chart is for.
 *
 * Short is drawn **below the axis, as a negative**, so the two legs oppose each other and
 * the gap between the ends of the stack reads as the net without anyone computing it. The
 * underlying figure the CFTC reports is a positive count of short contracts; it is negated
 * here for display only, and the hover template puts the sign back so a reader is never
 * shown "-98,000 short", which would say the opposite of what it means.
 *
 * Open interest sits on its own right-hand axis. It is an order of magnitude larger than
 * either leg, and on a shared axis it would flatten both bars into the baseline.
 */

export type PositioningSeries = {
  x: string[];
  long: (number | null)[];
  short: (number | null)[];
  openInterest: (number | null)[];
};

export function PositioningChart({
  data,
  height = 320,
}: {
  data: PositioningSeries;
  height?: number;
}) {
  const node = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!node.current) return;
    const el = node.current;
    let cancelled = false;

    const traces = [
      {
        x: data.x,
        y: data.long,
        name: "Managed money long",
        type: "bar" as const,
        marker: { color: SERIES.navy },
        hovertemplate: "%{y:,.0f} long<extra></extra>",
      },
      {
        x: data.x,
        // Negated for display only. `customdata` carries the figure as reported so the
        // hover reads "98,000 short" rather than a minus sign that would invert the claim.
        y: data.short.map((v) => (v === null ? null : -v)),
        customdata: data.short,
        name: "Managed money short",
        type: "bar" as const,
        marker: { color: SERIES.red },
        hovertemplate: "%{customdata:,.0f} short<extra></extra>",
      },
      {
        x: data.x,
        y: data.openInterest,
        name: "Open interest",
        type: "scatter" as const,
        mode: "lines" as const,
        connectgaps: false,
        yaxis: "y2",
        line: { color: SERIES.grey, width: 1.5 },
        hovertemplate: "%{y:,.0f} open interest<extra></extra>",
      },
    ];

    const layout: Record<string, unknown> = {
      ...baseLayout("contracts"),
      // `relative` stacks the positive and negative bars away from zero rather than
      // summing them, so a week's long and short each keep their own full height.
      barmode: "relative",
      bargap: 0.1,
      hovermode: "x unified",
      yaxis2: {
        overlaying: "y",
        side: "right" as const,
        showgrid: false,
        zeroline: false,
        title: { text: "open interest" },
      },
      margin: { l: 64, r: 64, t: 12, b: 40 },
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
  }, [data, height]);

  return <div ref={node} style={{ width: "100%", height }} />;
}
