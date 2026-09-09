"use client";

import { useEffect, useRef } from "react";

import { PLOT_CONFIG } from "@/theme/plotly";
import type { VesselRow } from "@/types/database";

/**
 * Latest vessel positions, coloured by reported ship class.
 *
 * Plotly's MapLibre trace with the free `open-street-map` style and no token — the same
 * choice `apps/dashboard` documents in root CLAUDE.md, which also records why
 * `Scattergeo` is not used: it renders a flat continent outline rather than a real map.
 * Keeping both front ends on one mapping stack means an exported exhibit matches.
 *
 * Plotly is imported inside the effect for the same reason as every other chart here: it
 * touches `self` at module evaluation and would break the prerender.
 *
 * **Class is as reported, not verified.** The AIS type code is hand-entered by the crew
 * and is often wrong or absent, so the legend says "reported as" and `other` covers both
 * a genuinely different vessel and a missing code.
 */

// Tanker red follows the convention marine traffic displays use, so a reader coming from
// one of those recognises a crude carrier without consulting the legend. The rest stay on
// the house palette.
const CLASS_COLOUR: Record<string, string> = {
  crude: "#c0392b",
  lng: "#e67e22",
  products: "#5b9bd5",
  other: "#95a5a6",
};

const CLASS_LABEL: Record<string, string> = {
  crude: "Tanker (reported)",
  products: "Cargo (reported)",
  lng: "LNG carrier (reported)",
  other: "Other or unreported",
};

export function VesselMap({
  vessels,
  height = 520,
}: {
  vessels: VesselRow[];
  height?: number;
}) {
  const node = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!node.current) return;
    const el = node.current;
    let cancelled = false;

    const classes = ["crude", "lng", "products", "other"];
    const traces = classes
      .map((cls) => {
        const rows = vessels.filter((v) => (v.ship_type ?? "other") === cls);
        if (rows.length === 0) return null;
        return {
          type: "scattermap" as const,
          mode: "markers" as const,
          name: `${CLASS_LABEL[cls]} (${rows.length})`,
          lat: rows.map((r) => r.lat),
          lon: rows.map((r) => r.lon),
          marker: {
            size: cls === "other" ? 7 : 11,
            color: CLASS_COLOUR[cls],
            // Rotated to each vessel's own course over ground, so an arrow points where
            // the ship is actually heading. A ship at anchor reports no meaningful
            // course, so it points north rather than claiming a heading it does not have
            // -- read the status, not the arrow, for a stationary vessel.
            angle: rows.map((r) => r.cog ?? 0),
            symbol: "triangle",
            allowoverlap: true,
          },
          customdata: rows.map((r) => [
            r.name ?? `MMSI ${r.mmsi}`,
            CLASS_LABEL[cls],
            r.nav_status ?? "status not reported",
            r.sog !== null ? `${r.sog} kn` : "speed not reported",
            r.cog !== null ? `${Math.round(r.cog)}°` : "course not reported",
            r.draught !== null && r.draught !== undefined
              ? `${r.draught} m draught`
              : "draught not reported",
            r.destination ?? "destination not reported",
          ]),
          hovertemplate:
            "<b>%{customdata[0]}</b><br>" +
            "%{customdata[1]}<br>" +
            "%{customdata[2]}<br>" +
            "%{customdata[3]} · %{customdata[4]}<br>" +
            "%{customdata[5]}<br>" +
            "Bound for %{customdata[6]}" +
            "<extra></extra>",
        };
      })
      .filter(Boolean);

    const layout = {
      map: {
        style: "carto-positron",
        // Centred between the Gulf and the Malacca Strait, zoomed out far enough to show
        // every monitored region at once.
        center: { lat: 25, lon: 40 },
        zoom: 1.4,
      },
      margin: { l: 0, r: 0, t: 0, b: 0 },
      legend: {
        orientation: "h" as const,
        yanchor: "top" as const,
        y: -0.02,
        xanchor: "left" as const,
        x: 0,
        font: { size: 11 },
      },
      paper_bgcolor: "white",
    };

    void import("plotly.js-dist-min").then(({ default: Plotly }) => {
      if (cancelled) return;
      void Plotly.newPlot(el, traces as never, layout as never, PLOT_CONFIG);
    });

    return () => {
      cancelled = true;
      void import("plotly.js-dist-min").then(({ default: Plotly }) => {
        Plotly.purge(el);
      });
    };
  }, [vessels]);

  return <div ref={node} style={{ width: "100%", height }} />;
}
