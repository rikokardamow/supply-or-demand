import { unstable_cache } from "next/cache";

import { fetchAllPages } from "@/data/paginate";
import { servingClient } from "@/data/supabase/server";
import type { SeriesLongRow } from "@/types/database";

/** How far back a panel reads by default. Five years covers a seasonal comparison. */
export const DEFAULT_YEARS = 5;

/**
 * A guard against a panel asking for an unreasonable amount, not a page size. The real
 * paging happens in `fetchAllPages`, because Supabase's 1,000-row cap is enforced
 * server-side and cannot be raised by the client.
 */
const HARD_LIMIT = 60_000;

function since(years: number): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  return date.toISOString();
}

async function querySeries(
  seriesIds: string[],
  years: number,
): Promise<SeriesLongRow[]> {
  if (seriesIds.length === 0) return [];

  const client = servingClient();
  return fetchAllPages<SeriesLongRow>(
    (from, to) =>
      client
        .from("series_long")
        .select("series_id, ts, value, unit, geo, freq, source, revision_date")
        .in("series_id", seriesIds)
        .gte("ts", since(years))
        // A stable total order across pages: ordering by ts alone leaves rows sharing a
        // timestamp (one per series) free to swap between pages, which duplicates some
        // and drops others.
        .order("ts", { ascending: true })
        .order("series_id", { ascending: true })
        .range(from, to),
    { hardLimit: HARD_LIMIT, label: `series_long [${seriesIds.join(", ")}]` },
  );
}

/** Tagged `series_long` -- see the note in seasonal.ts on `unstable_cache`. */
export const fetchSeries = unstable_cache(querySeries, ["series-long"], {
  tags: ["series_long"],
});

/** Group flat `series_long` rows into one array per series, preserving ts order. */
export function bySeries(
  rows: SeriesLongRow[],
): Map<string, SeriesLongRow[]> {
  const grouped = new Map<string, SeriesLongRow[]>();
  for (const row of rows) {
    const existing = grouped.get(row.series_id);
    if (existing) existing.push(row);
    else grouped.set(row.series_id, [row]);
  }
  return grouped;
}
