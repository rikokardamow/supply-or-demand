import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

/**
 * `POST /api/revalidate?tag=<table>` — called by the Python pipelines after a successful
 * publish so a page shows new data without waiting out its ISR window (Spec 32 §3,
 * Spec 33 §6).
 *
 * Authenticated by a shared secret in the `x-revalidate-secret` header. The secret is
 * compared in constant time: a plain `!==` leaks the length of the matching prefix
 * through timing, which is exactly the kind of endpoint worth getting right, since a
 * caller who guesses it can force unbounded rebuilds.
 *
 * `REVALIDATE_SECRET` is a *server-only* variable — deliberately not `NEXT_PUBLIC_`,
 * which Next inlines into the browser bundle. If it is unset the route refuses every
 * request rather than defaulting to open: an unconfigured deployment should be closed,
 * not unauthenticated.
 *
 * Only tags in `REVALIDATABLE_TAGS` are accepted. Nothing here is used to build a path,
 * so an arbitrary tag could not traverse anywhere, but an allowlist keeps a typo in a
 * pipeline from silently doing nothing and looking like it worked.
 */

const REVALIDATABLE_TAGS = new Set([
  "series_long",
  "seasonal",
  "wpsr_lines",
  "flows",
  "curve_settles",
  "spreads",
  "vessel_latest",
  "grp_scores",
  "grp_components",
]);

function constantTimeEquals(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i += 1) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export async function POST(request: Request): Promise<NextResponse> {
  const expected = process.env.REVALIDATE_SECRET;
  if (!expected) {
    return NextResponse.json(
      { revalidated: false, error: "REVALIDATE_SECRET is not configured" },
      { status: 503 },
    );
  }

  const provided = request.headers.get("x-revalidate-secret") ?? "";
  if (!constantTimeEquals(provided, expected)) {
    // No detail in the body: distinguishing "wrong secret" from "missing secret" tells a
    // caller which half to keep guessing at.
    return NextResponse.json({ revalidated: false }, { status: 401 });
  }

  const tag = new URL(request.url).searchParams.get("tag");
  if (!tag || !REVALIDATABLE_TAGS.has(tag)) {
    return NextResponse.json(
      { revalidated: false, error: `unknown tag: ${tag ?? "(none)"}` },
      { status: 400 },
    );
  }

  // Next 16 takes a second `profile` argument; the single-argument form is deprecated
  // and only still works with TypeScript errors suppressed. "max" is the recommended
  // value: mark the data stale and serve it stale-while-revalidate, so a publish never
  // leaves a visitor waiting on a cold render.
  revalidateTag(tag, "max");
  return NextResponse.json({ revalidated: true, tag, now: Date.now() });
}
