import type { SeriesLine } from "@/components/charts/TimeSeriesChart";
import type { FlowRow } from "@/types/database";

/**
 * Inter-PADD crude movements, shaped for charting.
 *
 * PADDs are the five Petroleum Administration for Defense Districts EIA still reports on:
 * 1 East Coast, 2 Midwest, 3 Gulf Coast, 4 Rocky Mountain, 5 West Coast. Crude moves
 * between them by pipeline, rail and tanker or barge, and EIA reports each mode
 * separately.
 *
 * **Volumes are monthly totals in thousand barrels, not a daily rate.** February is
 * therefore ~10% below an identical January by construction. They are left as reported
 * rather than converted to b/d: the EIA series is the monthly total, and dividing by month
 * length here would produce a figure that does not appear in the source.
 */

export const PADD_NAMES: Record<string, string> = {
  PADD1: "East Coast",
  PADD2: "Midwest",
  PADD3: "Gulf Coast",
  PADD4: "Rocky Mountain",
  PADD5: "West Coast",
};

export const MODES = ["pipeline", "rail", "tanker_barge"] as const;
export type Mode = (typeof MODES)[number];

export const MODE_LABELS: Record<Mode, string> = {
  pipeline: "Pipeline",
  rail: "Rail",
  tanker_barge: "Tanker and barge",
};

export function corridorLabel(from: string, to: string): string {
  return `${PADD_NAMES[from] ?? from} → ${PADD_NAMES[to] ?? to}`;
}

/**
 * Build one line per named corridor, on the union of every date any of them reports.
 *
 * The union matters: corridors start and stop at different times — PADD5→PADD3 by pipeline
 * has reported nothing since 2002 — and a corridor missing a month keeps its place on the
 * axis with a null rather than being dropped, so the line breaks instead of being drawn
 * straight across the gap.
 */
export function corridorLines(
  rows: FlowRow[],
  mode: Mode,
  corridors: [string, string][],
): SeriesLine[] {
  const inMode = rows.filter((r) => r.mode === mode);
  const dates = [...new Set(inMode.map((r) => r.ts))].sort();

  return corridors.flatMap(([from, to]) => {
    const byDate = new Map(
      inMode
        .filter((r) => r.from_node === from && r.to_node === to)
        .map((r) => [r.ts, r.value] as const),
    );
    if (byDate.size === 0) return [];
    return [
      {
        name: corridorLabel(from, to),
        x: dates,
        y: dates.map((d) => byDate.get(d) ?? null),
      },
    ];
  });
}

/**
 * Net movement between two PADDs, one direction minus the other.
 *
 * The gross legs answer "how much moved"; the net answers "which way the system leans",
 * and for Gulf Coast against Midwest those are different questions with different answers.
 * A month where either leg is unreported yields a null rather than treating the missing
 * leg as zero — an unreported flow and a flow of nothing are different claims.
 */
export function netLine(
  rows: FlowRow[],
  mode: Mode,
  from: string,
  to: string,
  name: string,
): SeriesLine[] {
  const inMode = rows.filter((r) => r.mode === mode);
  const out = new Map(
    inMode
      .filter((r) => r.from_node === from && r.to_node === to)
      .map((r) => [r.ts, r.value] as const),
  );
  const back = new Map(
    inMode
      .filter((r) => r.from_node === to && r.to_node === from)
      .map((r) => [r.ts, r.value] as const),
  );
  const dates = [...new Set([...out.keys(), ...back.keys()])].sort();
  if (dates.length === 0) return [];

  return [
    {
      name,
      x: dates,
      y: dates.map((d) => {
        const a = out.get(d);
        const b = back.get(d);
        return a === null || a === undefined || b === null || b === undefined
          ? null
          : a - b;
      }),
    },
  ];
}

/** Total moved by each mode per month, across every corridor it reports. */
export function modeTotals(rows: FlowRow[]): SeriesLine[] {
  const dates = [...new Set(rows.map((r) => r.ts))].sort();

  return MODES.flatMap((mode) => {
    const totals = new Map<string, number>();
    for (const row of rows) {
      if (row.mode !== mode || row.value === null) continue;
      totals.set(row.ts, (totals.get(row.ts) ?? 0) + row.value);
    }
    if (totals.size === 0) return [];
    return [
      {
        name: MODE_LABELS[mode],
        x: dates,
        // A month this mode reported nothing at all is a break, not a zero. Rail reported
        // no inter-PADD movement before 2010 because there was essentially none, and
        // drawing that as a flat zero line back to 1986 would state a measurement nobody
        // made.
        y: dates.map((d) => totals.get(d) ?? null),
      },
    ];
  });
}

/**
 * The corridors worth showing, chosen by volume rather than alphabetically.
 *
 * Measured against the published table on 2026-09-09: Gulf Coast → Midwest averages 41.7m
 * barrels a month and Midwest → Gulf Coast 16.1m, an order of magnitude above the rest.
 * Corridors whose last report predates 2020 are left out of the default view -- PADD5 →
 * PADD3 by pipeline stopped in 2002, and a dead line at the bottom of a chart is noise.
 */
export const PIPELINE_CORRIDORS: [string, string][] = [
  ["PADD3", "PADD2"],
  ["PADD2", "PADD3"],
  ["PADD4", "PADD2"],
  ["PADD2", "PADD4"],
  ["PADD4", "PADD3"],
];

export const RAIL_CORRIDORS: [string, string][] = [
  ["PADD2", "PADD5"],
  ["PADD2", "PADD1"],
  ["PADD2", "PADD3"],
  ["PADD4", "PADD3"],
  ["PADD4", "PADD1"],
];

export const MARINE_CORRIDORS: [string, string][] = [
  ["PADD5", "PADD3"],
  ["PADD3", "PADD1"],
  ["PADD2", "PADD3"],
  ["PADD2", "PADD1"],
  ["PADD1", "PADD3"],
];
