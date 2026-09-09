import { unstable_cache } from "next/cache";

import { fetchAllPages } from "@/data/paginate";
import { servingClient } from "@/data/supabase/server";
import type { EventRow, SanctionRow } from "@/types/database";

async function queryRecentEvents(limit: number): Promise<EventRow[]> {
  const { data, error } = await servingClient()
    .from("events")
    .select("event_id, ts, headline, source, url, tags, geo, commodity, severity")
    .order("ts", { ascending: false })
    .limit(limit);

  if (error) throw new Error(`events query failed: ${error.message}`);
  return (data ?? []) as EventRow[];
}

export const fetchRecentEvents = unstable_cache(queryRecentEvents, ["events"], {
  tags: ["events"],
});

export type EventCoverage = {
  source: string;
  events: number;
  distinct_days: number;
  first_ts: string | null;
  last_ts: string | null;
  severity_2_plus: number;
};

/**
 * Coverage per source, counted in Postgres.
 *
 * Not a daily-volume chart: OFAC's 2,506 events all carry one timestamp (the ingestion
 * date — a listing has no natural event time), so a volume line showed a single
 * artificial spike dwarfing every real source. Confirmed live 2026-09-09.
 */
async function queryEventCoverage(): Promise<EventCoverage[]> {
  const { data, error } = await servingClient()
    .from("event_source_coverage_v")
    .select("source, events, distinct_days, first_ts, last_ts, severity_2_plus");

  if (error) throw new Error(`event_source_coverage_v query failed: ${error.message}`);
  return (data ?? []) as EventCoverage[];
}

export const fetchEventCoverage = unstable_cache(queryEventCoverage, ["event-coverage"], {
  tags: ["events"],
});

/** Event counts per source per day, for the activity chart. */
async function queryEventCounts(days: number): Promise<EventRow[]> {
  const since = new Date();
  since.setDate(since.getDate() - days);
  const client = servingClient();

  return fetchAllPages<EventRow>(
    (from, to) =>
      client
        .from("events")
        .select("event_id, ts, headline, source, url, tags, geo, commodity, severity")
        .gte("ts", since.toISOString())
        .order("ts", { ascending: true })
        .order("event_id", { ascending: true })
        .range(from, to),
    { hardLimit: 20_000, label: "events window" },
  );
}

export const fetchEventWindow = unstable_cache(queryEventCounts, ["event-window"], {
  tags: ["events"],
});

async function querySanctionedVessels(limit: number): Promise<SanctionRow[]> {
  const { data, error } = await servingClient()
    .from("sanctioned_vessels_v")
    .select(
      "sanction_id, name, vess_type, vess_flag, vess_owner, call_sign, imo, programs, status, first_seen, last_seen",
    )
    .order("last_seen", { ascending: false })
    .limit(limit);

  if (error) throw new Error(`sanctioned_vessels_v query failed: ${error.message}`);
  return (data ?? []) as SanctionRow[];
}

export const fetchSanctionedVessels = unstable_cache(
  querySanctionedVessels,
  ["sanctioned-vessels"],
  { tags: ["sanctions"] },
);

export type LabelCount = { label: string; entries: number };
export type SanctionTotals = {
  entries: number;
  energy_related: number;
  with_imo: number;
};

/**
 * The flag and programme breakdowns, counted in Postgres.
 *
 * Selecting every row to count it in the page pulled 11 MB for twelve numbers -- mostly
 * `remarks` -- which also exceeded Next's 2 MB data-cache limit, so `unstable_cache`
 * silently refused to store it and every request requeried the whole table. Confirmed
 * live 2026-09-09: "items over 2MB can not be cached (11242947 bytes)".
 */
async function queryLabelCounts(view: string, limit: number): Promise<LabelCount[]> {
  const { data, error } = await servingClient()
    .from(view)
    .select("label, entries")
    .limit(limit);

  if (error) throw new Error(`${view} query failed: ${error.message}`);
  return (data ?? []) as LabelCount[];
}

export const fetchFlagCounts = unstable_cache(
  (limit: number) => queryLabelCounts("sanction_flag_counts_v", limit),
  ["sanction-flags"],
  { tags: ["sanctions"] },
);

export const fetchProgrammeCounts = unstable_cache(
  (limit: number) => queryLabelCounts("sanction_programme_counts_v", limit),
  ["sanction-programmes"],
  { tags: ["sanctions"] },
);

async function querySanctionTotals(): Promise<SanctionTotals> {
  const { data, error } = await servingClient()
    .from("sanction_totals_v")
    .select("entries, energy_related, with_imo")
    .limit(1);

  if (error) throw new Error(`sanction_totals_v query failed: ${error.message}`);
  return (data?.[0] as SanctionTotals | undefined) ?? {
    entries: 0,
    energy_related: 0,
    with_imo: 0,
  };
}

export const fetchSanctionTotals = unstable_cache(
  querySanctionTotals,
  ["sanction-totals"],
  { tags: ["sanctions"] },
);
