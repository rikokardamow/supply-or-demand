/**
 * Read every row of a PostgREST query, a page at a time.
 *
 * **This is not an optimisation — without it charts are silently wrong.** Supabase caps
 * a response at `max-rows` (1,000 on this project) *server-side*, and a client-supplied
 * `Range` header cannot raise it. Confirmed live 2026-09-09: `agsi.DE.full_pct` holds
 * 3,147 rows, and a request with `Range: 0-49999` returned exactly 1,000 with
 * `Content-Range: 0-999/3147`. The chart drew those 1,000 points and stopped in early
 * 2025 with no gap, no error and no visual clue — a truncated series looks exactly like
 * a series that ended.
 *
 * `hardLimit` is a guard, not a target: a query that would need hundreds of pages should
 * be narrowed (a date filter, fewer series) rather than looped, so exceeding it raises
 * instead of quietly returning a partial answer — which is the very failure this exists
 * to prevent.
 */
const PAGE_SIZE = 1000;

export async function fetchAllPages<T>(
  // PromiseLike, not Promise: Supabase's query builder is a thenable that only becomes a
  // real promise once awaited, so it does not satisfy `Promise`.
  page: (
    from: number,
    to: number,
  ) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
  { hardLimit = 100_000, label = "query" }: { hardLimit?: number; label?: string } = {},
): Promise<T[]> {
  const rows: T[] = [];

  for (let from = 0; from < hardLimit; from += PAGE_SIZE) {
    const { data, error } = await page(from, from + PAGE_SIZE - 1);
    if (error) throw new Error(`${label} failed: ${error.message}`);

    const batch = data ?? [];
    rows.push(...batch);
    // A short page is the last page.
    if (batch.length < PAGE_SIZE) return rows;
  }

  throw new Error(
    `${label} exceeded ${hardLimit} rows -- narrow the query rather than returning a ` +
      "partial series, which would look complete on a chart",
  );
}
