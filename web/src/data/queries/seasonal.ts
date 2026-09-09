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
export async function fetchSeasonalBand(seriesId: string): Promise<SeasonalRow[]> {
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
