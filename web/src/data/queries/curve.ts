import { unstable_cache } from "next/cache";

import { fetchAllPages } from "@/data/paginate";
import { servingClient } from "@/data/supabase/server";
import type { CurveSettleRow, SpreadRow } from "@/types/database";

/**
 * The forward curve for one root, on its most recent trade date.
 *
 * Two queries rather than one: PostgREST has no `distinct on`, so the latest trade date
 * is read first and then used to filter. Sorting by contract code would order
 * alphabetically (F2027 before X2026) rather than by delivery month, so the rows come
 * back ordered by `expiry` where it exists and by contract otherwise.
 */
async function queryCurve(root: string): Promise<CurveSettleRow[]> {
  const client = servingClient();

  const latest = await client
    .from("curve_settles")
    .select("trade_date")
    .eq("root", root)
    .order("trade_date", { ascending: false })
    .limit(1);

  if (latest.error) {
    throw new Error(`curve_settles query failed for ${root}: ${latest.error.message}`);
  }
  const tradeDate = latest.data?.[0]?.trade_date;
  if (!tradeDate) return [];

  const { data, error } = await client
    .from("curve_settles")
    .select("root, trade_date, contract, expiry, settle, oi, source")
    .eq("root", root)
    .eq("trade_date", tradeDate)
    .order("contract", { ascending: true })
    .limit(500);

  if (error) {
    throw new Error(`curve_settles query failed for ${root}: ${error.message}`);
  }

  const rows = (data ?? []) as CurveSettleRow[];
  return rows.sort(byDeliveryMonth);
}

/** Futures month codes, in calendar order — the exchange convention, not alphabetical. */
const MONTH_CODES = "fghjkmnquvxz";

/**
 * Sort `X2026` before `F2027`: the code's trailing year first, then its month letter's
 * position in the exchange's own sequence. Sorting the raw string would put every
 * January ahead of every November regardless of year, folding the curve back on itself.
 */
function byDeliveryMonth(a: CurveSettleRow, b: CurveSettleRow): number {
  const key = (contract: string) => {
    const month = contract.slice(0, 1).toLowerCase();
    const year = contract.slice(1);
    return `${year}${String(MONTH_CODES.indexOf(month)).padStart(2, "0")}`;
  };
  return key(a.contract).localeCompare(key(b.contract));
}

export const fetchCurve = unstable_cache(queryCurve, ["curve-settles"], {
  tags: ["curve_settles"],
});

/**
 * `sinceYears` is measured from today, not from the data's own end. That matters here:
 * this series stops in April 2024 (EIA discontinued the route), so a two-year window
 * would return nothing at all and the panel would read "no spreads" rather than showing
 * a real history that has ended. Ten years spans the useful record without asking for
 * fifty sequential pages of 1980s data.
 */
async function querySpreads(
  root: string,
  legs: string[],
  sinceYears = 10,
): Promise<SpreadRow[]> {
  const client = servingClient();
  const from = new Date();
  from.setFullYear(from.getFullYear() - sinceYears);
  const since = from.toISOString().slice(0, 10);
  return fetchAllPages<SpreadRow>(
    (from, to) =>
      client
        .from("spreads_v")
        .select("root, trade_date, legs, value")
        .eq("root", root)
        .in("legs", legs)
        .gte("trade_date", since)
        // trade_date alone is not a total order here -- each date carries one row per
        // leg, and without the tiebreak they shuffle between pages.
        .order("trade_date", { ascending: true })
        .order("legs", { ascending: true })
        .range(from, to),
    { hardLimit: 120_000, label: `spreads_v ${root}` },
  );
}

export const fetchSpreads = unstable_cache(querySpreads, ["spreads"], {
  tags: ["spreads"],
});
