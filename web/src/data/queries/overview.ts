import { unstable_cache } from "next/cache";

import { servingClient } from "@/data/supabase/server";

export type Headline = {
  key: string;
  label: string;
  unit: string | null;
  value: number | null;
  /** Change against the previous observation, in the series' own unit. */
  change: number | null;
  /** Distance from the seasonal median at today's day-of-year, as a percentage. */
  vsMedian: number | null;
  ts: string | null;
  href: string;
};

/** The figures a reader should see before any chart, and where each one lives. */
const HEADLINES: {
  key: string;
  seriesId: string;
  label: string;
  href: string;
  seasonal?: boolean;
}[] = [
  { key: "wti", seriesId: "fut.cl.f01.close", label: "WTI crude", href: "/prices/cl" },
  { key: "brent", seriesId: "fut.lco.f01.close", label: "Brent crude", href: "/prices/lco" },
  { key: "gas", seriesId: "fut.ng.f01.close", label: "Henry Hub", href: "/prices/ng" },
  {
    key: "eu_storage",
    seriesId: "agsi.EU.full_pct",
    label: "EU gas storage",
    href: "/gas",
    seasonal: true,
  },
  {
    key: "us_crude",
    seriesId: "WCESTUS1",
    label: "US crude stocks",
    href: "/balances",
    seasonal: true,
  },
  {
    key: "rigs",
    seriesId: "bh.rigs.united_states.total",
    label: "US rig count",
    href: "/supply",
  },
];

/**
 * The last two observations of one series, newest first.
 *
 * Two rather than one because a level without its change is half a number — a reader
 * wants to know both where it is and which way it moved.
 */
async function lastTwo(seriesId: string) {
  const { data, error } = await servingClient()
    .from("series_long")
    .select("ts, value, unit")
    .eq("series_id", seriesId)
    .order("ts", { ascending: false })
    .limit(2);

  if (error) throw new Error(`overview query failed for ${seriesId}: ${error.message}`);
  return data ?? [];
}

/**
 * The seasonal median at today's day-of-year, for series that have a published band.
 *
 * `core.seasonal` normalises onto a non-leap reference year and drops 29 February, so a
 * leap day is clamped to the 28th — the same clamp `core/publish.py` applies, and for the
 * same reason.
 */
async function medianToday(seriesId: string): Promise<number | null> {
  const now = new Date();
  const month = now.getUTCMonth() + 1;
  const day = month === 2 && now.getUTCDate() === 29 ? 28 : now.getUTCDate();
  const doy = Math.floor(
    (Date.UTC(2001, month - 1, day) - Date.UTC(2001, 0, 0)) / 86_400_000,
  );

  const { data, error } = await servingClient()
    .from("seasonal_v")
    .select("median")
    .eq("series_id", seriesId)
    .eq("doy", doy)
    .limit(1);

  if (error) return null;
  return (data?.[0]?.median as number | undefined) ?? null;
}

async function queryHeadlines(): Promise<Headline[]> {
  return Promise.all(
    HEADLINES.map(async (spec) => {
      const [rows, median] = await Promise.all([
        lastTwo(spec.seriesId),
        spec.seasonal ? medianToday(spec.seriesId) : Promise.resolve(null),
      ]);

      const latest = rows[0];
      const previous = rows[1];
      const value = (latest?.value as number | undefined) ?? null;

      return {
        key: spec.key,
        label: spec.label,
        href: spec.href,
        unit: (latest?.unit as string | undefined) ?? null,
        value,
        change:
          value !== null && previous?.value !== null && previous?.value !== undefined
            ? value - (previous.value as number)
            : null,
        // A zero median has no percentage distance -- dividing would give an infinity
        // that reads like a real figure.
        vsMedian:
          value !== null && median !== null && median !== 0
            ? (value / median - 1) * 100
            : null,
        ts: (latest?.ts as string | undefined) ?? null,
      };
    }),
  );
}

export const fetchHeadlines = unstable_cache(queryHeadlines, ["headlines"], {
  tags: ["series_long", "seasonal"],
});
