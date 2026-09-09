import { unstable_cache } from "next/cache";

import { servingClient } from "@/data/supabase/server";
import type { WpsrLineRow } from "@/types/database";

/**
 * The WPSR at-a-glance table for the most recent week.
 *
 * `wpsr_latest_v` already filters to `max(week_ending)` and orders by `line_order`, so
 * this adds no logic of its own — Spec 32 §1 keeps the maths in Python and leaves the
 * views to filtering and joining. The explicit `order` is belt and braces: a view's own
 * ORDER BY is not guaranteed to survive PostgREST's query planning.
 */
async function queryWpsrLines(): Promise<WpsrLineRow[]> {
  const { data, error } = await servingClient()
    .from("wpsr_latest_v")
    .select(
      "week_ending, line, label, unit, value, wow, yoy_pct, vs_median_pct, line_order",
    )
    .order("line_order", { ascending: true });

  if (error) {
    throw new Error(`wpsr_latest_v query failed: ${error.message}`);
  }

  return (data ?? []) as WpsrLineRow[];
}

/** Tagged `wpsr_lines` -- see the note in seasonal.ts on `unstable_cache`. */
export const fetchWpsrLines = unstable_cache(queryWpsrLines, ["wpsr-lines"], {
  tags: ["wpsr_lines"],
});
