import { unstable_cache } from "next/cache";

import { servingClient } from "@/data/supabase/server";
import type { SeasonalRow } from "@/types/database";

/**
 * One series' seasonal band, ordered by day-of-year.
 *
 * Spec 33 §6: components never call `supabase.from()` directly -- every table gets one
 * typed function here, so a schema change breaks in one place rather than in every panel
 * that happened to query it.
 *
 * A full year is 365 rows (`core.seasonal` drops 29 February), so this returns the whole
 * curve rather than paginating. Supabase's own default cap is 1,000 rows, comfortably
 * above that, but the limit is explicit so a future caller widening the query notices it.
 */
async function querySeasonalBand(seriesId: string): Promise<SeasonalRow[]> {
  const { data, error } = await servingClient()
    .from("seasonal_v")
    .select("series_id, doy, band_min, band_max, median, current, prior, years, unit")
    .eq("series_id", seriesId)
    .order("doy", { ascending: true })
    .limit(400);

  if (error) {
    // Surfacing the series id matters: "no rows" and "this series does not exist" look
    // identical on a chart otherwise.
    throw new Error(`seasonal_v query failed for ${seriesId}: ${error.message}`);
  }

  return (data ?? []) as SeasonalRow[];
}

/**
 * Tagged `seasonal`, so `POST /api/revalidate?tag=seasonal` refreshes it the moment a
 * pipeline publishes rather than at the end of the page's own ISR window.
 *
 * `unstable_cache` is deprecated in Next 16 in favour of the `use cache` directive, but
 * `use cache` requires Cache Components, and enabling that removes the `revalidate`
 * route segment config this app relies on. Revisit together, not piecemeal.
 */
export const fetchSeasonalBand = unstable_cache(
  querySeasonalBand,
  ["seasonal-band"],
  { tags: ["seasonal"] },
);
