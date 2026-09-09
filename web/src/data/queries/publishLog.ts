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

/**
 * The latest publish of one table *by one pipeline*.
 *
 * `latest_publish_v` is `distinct on (table_name)`, so for a table several pipelines
 * write it returns whichever ran last — `serving.seasonal` is published by both wpsr and
 * gie, and a WPSR panel showing GIE's timestamp would be wrong in exactly the way an
 * as-of stamp exists to prevent. This goes to `publish_log` directly, which carries
 * `pipeline`, so each panel gets the provenance of the rows it actually draws.
 */
export async function fetchLatestPublishBy(
  tableName: string,
  pipeline: string,
): Promise<PublishLogRow | null> {
  const { data, error } = await servingClient()
    .from("publish_log")
    .select("table_name, as_of, source_note, published_at")
    .eq("table_name", tableName)
    .eq("pipeline", pipeline)
    .order("published_at", { ascending: false })
    .limit(1);

  if (error) {
    throw new Error(
      `publish_log query failed for ${tableName}/${pipeline}: ${error.message}`,
    );
  }

  return (data?.[0] as PublishLogRow | undefined) ?? null;
}
