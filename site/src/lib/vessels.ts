import { servingClient } from "@/lib/supabase";

/**
 * Vessel positions for the hero globe.
 *
 * These are the real latest AIS fixes behind data.kardamow.com's vessel map, not a
 * decorative scatter. That is the whole reason the globe is worth drawing: a template can
 * have a rendered sphere, but it cannot have this evening's tanker positions on it.
 *
 * **Coverage is terrestrial AIS, so empty ocean means no receiver, not no ships.** The
 * page says so rather than implying the map is complete.
 */

export type Point = { lat: number; lon: number; tanker: boolean };

export async function fetchVesselPoints(limit = 900): Promise<Point[]> {
  try {
    const { data, error } = await servingClient()
      .from("vessel_latest_v")
      .select("lat, lon, ship_type")
      .limit(limit);
    if (error || !data) return [];

    return data
      .filter(
        (r): r is { lat: number; lon: number; ship_type: string | null } =>
          typeof r.lat === "number" &&
          typeof r.lon === "number" &&
          Number.isFinite(r.lat) &&
          Number.isFinite(r.lon),
      )
      .map((r) => ({
        lat: r.lat,
        lon: r.lon,
        // The pipeline's own classes, confirmed against the live table on 2026-09-09:
        // "crude", "products" and "other". An earlier version tested for the substring
        // "tanker", which matches none of them — so every vessel fell through to the
        // unclassified style and the tankers, which are the ones this publication is
        // actually about, were the least visible thing on the globe.
        //
        // Class is as the vessel reports it, never verified, so it decides a colour and
        // nothing more.
        tanker: r.ship_type === "crude" || r.ship_type === "products",
      }));
  } catch {
    // A landing page renders without its globe rather than failing.
    return [];
  }
}
