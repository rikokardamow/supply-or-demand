"use client";

import { useEffect, useRef } from "react";
import type PlotlyModule from "plotly.js-dist-min";

import { formatDayOfYear } from "@/lib/format";
import { GRID, MUTED, SERIES } from "@/theme/plotly";
import type { SeasonalRow } from "@/types/database";

type PlotlyData = Parameters<typeof PlotlyModule.newPlot>[1];
type PlotlyLayout = Parameters<typeof PlotlyModule.newPlot>[2];

/**
 * The seasonal band exhibit: a grey min-max band, an orange median, this year's track in
 * navy and last year's in light blue -- the same encoding as
 * `core.theme.seasonal_range_chart`, so a panel exported from here and one exported from
 * the Python side read identically.
 *
 * `"use client"` alone is not enough: Plotly touches `self` at *module evaluation*, and
 * Next still evaluates a client component's module during prerender, so a top-level
 * `import Plotly from "plotly.js-dist-min"` fails the build with `ReferenceError: self is
 * not defined`. It is imported lazily inside the effect instead, which only ever runs in
 * the browser -- the same outcome Spec 33 §3's "dynamic import, ssr: false" asks for,
 * without a wrapper component. The data arrives as a prop, already fetched server-side:
 * the chart never queries anything itself (Spec 33 §6).
 *
 * The chart paints no title of its own: `Panel` owns the heading (root CLAUDE.md's chart
 * house style). Every in-chart string stays on the Inter body stack -- a number must
 * never render in the serif.
 */

const BODY_STACK =
  'Inter, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export function SeasonalChart({
  rows,
  unit,
  bandYears,
}: {
  rows: SeasonalRow[];
  unit?: string | null;
  bandYears?: number | null;
}) {
  const node = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!node.current) return;
    const el = node.current;
    let cancelled = false;

    const x = rows.map((r) => formatDayOfYear(r.doy ?? 1));
    const bandLabel = bandYears ? `${bandYears}-year range` : "Seasonal range";

    const traces: PlotlyData = [
      // The band is drawn as min, then max filled back down to it. Order matters:
      // `fill: "tonexty"` fills against the *previous* trace.
      {
        x,
        y: rows.map((r) => r.band_min),
        name: bandLabel,
        type: "scatter",
        mode: "lines",
        line: { width: 0, color: SERIES.band },
        hoverinfo: "skip",
        showlegend: false,
      },
      {
        x,
        y: rows.map((r) => r.band_max),
        name: bandLabel,
        type: "scatter",
        mode: "lines",
        line: { width: 0, color: SERIES.band },
        fill: "tonexty",
        fillcolor: SERIES.band,
        hoverinfo: "skip",
      },
      {
        x,
        y: rows.map((r) => r.median),
        name: "Median",
        type: "scatter",
        mode: "lines",
        line: { color: SERIES.orange, width: 1.5, dash: "dot" },
      },
      {
        x,
        y: rows.map((r) => r.prior),
        name: "Last year",
        type: "scatter",
        mode: "lines",
        line: { color: SERIES.lightBlue, width: 1.5 },
      },
      {
        // `current` is null for days that have not happened yet -- Plotly breaks the
        // line there rather than drawing a flat projection to 31 December.
        x,
        y: rows.map((r) => r.current),
        name: "This year",
        type: "scatter",
        mode: "lines",
        line: { color: SERIES.navy, width: 2.5 },
        connectgaps: false,
      },
    ];

    const layout: PlotlyLayout = {
      font: { family: BODY_STACK, size: 12, color: MUTED },
      paper_bgcolor: "white",
      plot_bgcolor: "white",
      margin: { l: 56, r: 24, t: 12, b: 40 },
      hovermode: "x unified",
      legend: {
        orientation: "h",
        yanchor: "bottom",
        y: 1.0,
        xanchor: "left",
        x: 0,
      },
      xaxis: {
        showgrid: false,
        tickmode: "array",
        // One tick per month rather than per day: 365 categorical labels are unreadable.
        tickvals: rows
          .filter((r) => {
            const d = new Date(Date.UTC(2001, 0, r.doy ?? 1));
            return d.getUTCDate() === 1;
          })
          .map((r) => formatDayOfYear(r.doy ?? 1)),
      },
      yaxis: {
        gridcolor: GRID,
        zeroline: false,
        title: unit ? { text: unit, font: { family: BODY_STACK } } : undefined,
      },
    };

    // Imported here, not at module scope: see the note above.
    void import("plotly.js-dist-min").then(({ default: Plotly }) => {
      // The effect can be torn down before the chunk resolves (a fast re-render, or the
      // user navigating away); plotting into a detached node would leak it.
      if (cancelled) return;
      void Plotly.newPlot(el, traces, layout, {
        displayModeBar: false,
        responsive: true,
      });
    });

    return () => {
      cancelled = true;
      void import("plotly.js-dist-min").then(({ default: Plotly }) => {
        Plotly.purge(el);
      });
    };
  }, [rows, unit, bandYears]);

  return <div ref={node} style={{ width: "100%", height: 380 }} />;
}
