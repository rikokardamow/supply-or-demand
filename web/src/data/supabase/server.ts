import { createClient } from "@supabase/supabase-js";

/**
 * Supabase client for server components.
 *
 * Uses the **publishable (anon) key**, exactly like the browser would. There is no
 * service-role key anywhere in this app: every `serving.*` table has RLS granting `anon`
 * SELECT and nothing else (Spec 32 §4), so the anon key is already sufficient to read
 * everything the UI shows, and introducing a privileged key would create a
 * secret-handling problem for no capability gain.
 *
 * `db.schema` is `serving`, not `public` -- the schema is exposed on the Data API but is
 * not the default, so `supabase.from("seasonal_v")` would otherwise resolve against
 * `public` and fail with PGRST205.
 */
export function servingClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    // Failing loudly beats rendering an empty chart that looks like "no data".
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set -- copy .env.example to .env.local",
    );
  }

  return createClient(url, key, { db: { schema: "serving" } });
}
