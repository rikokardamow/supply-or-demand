import { NextResponse } from "next/server";

import { fetchHeadlines } from "@/data/queries/overview";

/**
 * The headline figures as JSON, for the ticker rail to re-check without a page reload.
 *
 * `fetchHeadlines` is already wrapped in `unstable_cache` and tagged, so this route
 * serves whatever the last publish put there and costs no Supabase round trip in
 * between. A reader keeping the page open sees a new figure once the pipeline that
 * produces it publishes and calls `/api/revalidate` -- not on a timer of its own.
 *
 * Read-only, no parameters, and it exposes only what the front page already renders in
 * its HTML, so there is nothing here to authenticate.
 */
export const revalidate = 300;

export async function GET() {
  return NextResponse.json({ headlines: await fetchHeadlines() });
}
