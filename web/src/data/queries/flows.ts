import { unstable_cache } from "next/cache";

import { fetchAllPages } from "@/data/paginate";
import { servingClient } from "@/data/supabase/server";
import type { FlowRow } from "@/types/database";

/**
 * Directional flows from `serving.flows`.
 *
 * `mode` is part of the primary key, not a label: EIA reports the same corridor separately
 * by pipeline, rail and tanker/barge, and summing them without saying so would hide the
 * mode shift that is usually the story — Bakken crude moved by rail because there was no
 * pipe, and stopped when there was.
 */

const HARD_LIMIT = 40_000;

async function queryFlows(source: string, modes: string[]): Promise<FlowRow[]> {
  const client = servingClient();
  return fetchAllPages<FlowRow>(
    (from, to) =>
      client
        .from("flows")
        .select("source, from_node, to_node, ts, period, value, unit, mode")
        .eq("source", source)
        .in("mode", modes)
        // A stable total order across pages. Ordering by ts alone leaves rows sharing a
        // timestamp free to swap between pages, which duplicates some and drops others.
        .order("ts", { ascending: true })
        .order("mode", { ascending: true })
        .order("from_node", { ascending: true })
        .order("to_node", { ascending: true })
        .range(from, to),
    { hardLimit: HARD_LIMIT, label: `flows [${source}: ${modes.join(", ")}]` },
  );
}

/** Tagged `flows` -- see the note in seasonal.ts on `unstable_cache`. */
export const fetchFlows = unstable_cache(queryFlows, ["flows"], { tags: ["flows"] });
