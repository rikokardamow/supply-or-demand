import type { SeriesLine } from "@/components/charts/TimeSeriesChart";
import { bySeries } from "@/data/queries/series";
import type { SeriesLongRow } from "@/types/database";

/**
 * Turn flat `series_long` rows into chart lines, in the order the caller named them.
 *
 * Order matters: `TimeSeriesChart` assigns the palette by position, and navy — the
 * primary — is first. Preserving the caller's order keeps the colour that reads as
 * "the main line" on the series the panel is actually about, rather than on whichever
 * series happened to sort first.
 *
 * A named series absent from the data is dropped rather than drawn empty: an empty
 * legend entry claims a series exists and has no values, which is a different statement
 * from "this series was never published".
 */
export function toLines(
  rows: SeriesLongRow[],
  labels: Record<string, string>,
  options: { secondary?: string[] } = {},
): SeriesLine[] {
  const grouped = bySeries(rows);
  const secondary = new Set(options.secondary ?? []);

  return Object.entries(labels).flatMap(([seriesId, name]) => {
    const points = grouped.get(seriesId);
    if (!points || points.length === 0) return [];
    return [
      {
        name,
        x: points.map((p) => p.ts),
        y: points.map((p) => p.value),
        secondary: secondary.has(seriesId),
      },
    ];
  });
}

/** The unit shared by the named series, or null when they disagree. */
export function commonUnit(
  rows: SeriesLongRow[],
  seriesIds?: string[],
): string | null {
  const wanted = seriesIds ? new Set(seriesIds) : null;
  const units = new Set(
    rows
      .filter((r) => !wanted || wanted.has(r.series_id))
      .map((r) => r.unit)
      .filter((u): u is string => Boolean(u)),
  );
  // Two units on one axis would silently mislead -- better no label than a wrong one.
  return units.size === 1 ? [...units][0] : null;
}
