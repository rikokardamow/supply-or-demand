import { servingClient } from "@/data/supabase/server";
import type { PublishLogRow } from "@/types/database";

/**
 * The most recent publish for each serving table.
 *
 * Spec 33 §6: a panel's as-of always comes from here, never from `max(ts)` of the series
 * it draws. The two differ in exactly the case that matters -- a source that has stopped
 * updating still has a max(ts), and inferring freshness from it would report a dead feed
 * as current.
 */
export async function fetchLatestPublishes(): Promise<PublishLogRow[]> {
  const { data, error } = await servingClient()
    .from("latest_publish_v")
    .select("table_name, as_of, source_note, published_at");

  if (error) {
    throw new Error(`latest_publish_v query failed: ${error.message}`);
  }

  return (data ?? []) as PublishLogRow[];
}

export async function fetchLatestPublish(
  tableName: string,
): Promise<PublishLogRow | null> {
  const rows = await fetchLatestPublishes();
  return rows.find((row) => row.table_name === tableName) ?? null;
}
