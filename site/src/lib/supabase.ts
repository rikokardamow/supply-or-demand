import { createClient } from "@supabase/supabase-js";

/**
 * The same read-only serving schema data.kardamow.com uses.
 *
 * Anon key only, and every `serving.*` table grants SELECT to anon under RLS -- this page
 * shows figures that are already public on the data site, so there is nothing here that
 * needs a privileged key.
 */
export function servingClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Supabase URL and anon key must both be set");
  return createClient(url, key, { db: { schema: "serving" }, auth: { persistSession: false } });
}
