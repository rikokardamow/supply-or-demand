import { unstable_cache } from "next/cache";

import { fetchAllPages } from "@/data/paginate";
import { servingClient } from "@/data/supabase/server";
import type { VesselRow } from "@/types/database";

/**
 * Every vessel's latest position.
 *
 * Paged, because a busy capture puts several thousand vessels in the table and Supabase
 * caps a response at 1,000 rows server-side -- a truncated map looks like a quiet ocean
 * rather than a missing page.
 */
async function queryVessels(): Promise<VesselRow[]> {
  const client = servingClient();
  return fetchAllPages<VesselRow>(
    (from, to) =>
      client
        .from("vessel_latest_v")
        .select("mmsi, ts, lat, lon, sog, cog, nav_status, ship_type, draught, name, destination")
        .order("mmsi", { ascending: true })
        .range(from, to),
    { hardLimit: 60_000, label: "vessel_latest_v" },
  );
}

export const fetchVessels = unstable_cache(queryVessels, ["vessels"], {
  tags: ["vessel_latest"],
});
