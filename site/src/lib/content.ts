import { servingClient } from "@/lib/supabase";

/**
 * The two live sources this page draws on.
 *
 * Both are real: the figures come from the same published tables data.kardamow.com serves,
 * and the writing comes from the Substack's own RSS. Nothing on the page is a placeholder
 * or a hard-coded number, which is the point — a research site whose landing page invents
 * its own statistics has undermined itself before a reader reaches the second screen.
 */

export type Figure = {
  label: string;
  value: number | null;
  unit: string | null;
  change: number | null;
  digits: number;
};

const FIGURES: { id: string; label: string; digits: number }[] = [
  { id: "fut.lco.f01.close", label: "Brent", digits: 2 },
  { id: "fut.cl.f01.close", label: "WTI", digits: 2 },
  { id: "agsi.EU.full_pct", label: "EU gas storage", digits: 1 },
];

/**
 * The latest two observations of each headline series, so the page can show a level and
 * the direction it moved.
 *
 * Failures return an empty list rather than throwing. This is a landing page: if Supabase
 * is unreachable the correct outcome is a page that renders without its figures, not a
 * 500. The section is omitted entirely rather than showing dashes, because a row of
 * en dashes says "broken" where showing nothing says nothing.
 */
export async function fetchFigures(): Promise<Figure[]> {
  try {
    const client = servingClient();
    const rows = await Promise.all(
      FIGURES.map(async (spec) => {
        const { data, error } = await client
          .from("series_long")
          .select("value, unit")
          .eq("series_id", spec.id)
          .order("ts", { ascending: false })
          .limit(2);
        if (error || !data || data.length === 0) return null;

        const latest = data[0].value as number | null;
        const previous = (data[1]?.value ?? null) as number | null;
        return {
          label: spec.label,
          value: latest,
          unit: (data[0].unit as string | null) ?? null,
          change:
            latest !== null && previous !== null ? latest - previous : null,
          digits: spec.digits,
        };
      }),
    );
    return rows.filter((r): r is Figure => r !== null);
  } catch {
    return [];
  }
}

/**
 * A feed-supplied URL, or null if it is not plainly http(s).
 *
 * **React does not protect an `href`.** It escapes text content, which is why the parsing
 * below can strip tags without an HTML parser — but a `javascript:` URI placed in an href
 * is rendered as-is, with only a development-mode console warning. So a feed item carrying
 * `<link>javascript:...</link>` would produce a link on the public page that executes
 * script when a reader clicks it.
 *
 * The feed is the author's own Substack, so the realistic threat is not that Substack
 * turns hostile: it is a compromised account, a tampering proxy, or a CDN serving someone
 * else's response. Remote input rendered into an attribute gets validated regardless of
 * who is nominally on the other end.
 *
 * Parsed with `URL` rather than matched with a regex. Browsers ignore whitespace and
 * control characters inside a scheme, so `java	script:` navigates exactly like
 * `javascript:` while defeating a naive `startsWith("javascript:")` check; `URL` applies
 * the same normalisation the browser will.
 */
export function httpUrlOrNull(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.href
      : null;
  } catch {
    // Not a parseable absolute URL — including protocol-relative "//host", which has no
    // scheme of its own and would inherit the page's.
    return null;
  }
}

/**
 * Decode the HTML entities a feed can carry.
 *
 * Numeric entities are handled generally rather than from a hand-written list: an earlier
 * version decoded `&#8217;` but not its opening twin `&#8216;`, so an opening curly quote
 * rendered as literal `&#8216;` on the page.
 *
 * **`&amp;` is decoded last, and that ordering is load-bearing.** Decoding it first would
 * turn `&amp;lt;script&amp;gt;` into `&lt;script&gt;` and then into a real tag — the
 * classic double-decode mistake.
 */
export function decodeEntities(value: string): string {
  return value
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) =>
      String.fromCodePoint(parseInt(hex, 16)),
    )
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(Number(dec)))
    .replace(/&lsquo;/g, "‘")
    .replace(/&rsquo;/g, "’")
    .replace(/&ldquo;/g, "“")
    .replace(/&rdquo;/g, "”")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&nbsp;/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

export type Post = {
  title: string;
  url: string;
  date: string | null;
  /**
   * The post's own standfirst from the feed.
   *
   * Worth carrying rather than showing titles alone: these are the strongest evidence of
   * the method on the whole page. "A 438-gigawatt line, five times the grid's all-time
   * peak, halved the moment a deposit was demanded" argues for itself in a way that a
   * title cannot.
   */
  dek: string | null;
};

/**
 * Recent posts, read from the Substack's public RSS.
 *
 * Parsed with a regex rather than an XML library. That is usually the wrong call, but the
 * shape here is fixed, the feed is one known publication rather than arbitrary input, and
 * the alternative is a dependency for four fields. If the feed ever fails to parse, the
 * section disappears rather than the build breaking.
 */
export async function fetchPosts(limit = 5): Promise<Post[]> {
  try {
    const response = await fetch("https://kardamow.substack.com/feed", {
      // Revalidated on the same hour as the page. A newsletter does not publish more often
      // than that, and an uncached fetch would hit Substack on every render.
      next: { revalidate: 3600 },
    });
    if (!response.ok) return [];
    const xml = await response.text();

    const items = xml.split("<item>").slice(1);
    const posts: Post[] = [];
    for (const item of items) {
      const title =
        item.match(/<title><!\[CDATA\[([\s\S]*?)\]\]><\/title>/)?.[1] ??
        item.match(/<title>([\s\S]*?)<\/title>/)?.[1];
      const url =
        item.match(/<link><!\[CDATA\[([\s\S]*?)\]\]><\/link>/)?.[1] ??
        item.match(/<link>([\s\S]*?)<\/link>/)?.[1];
      const date = item.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1] ?? null;
      const rawDek =
        item.match(
          /<description><!\[CDATA\[([\s\S]*?)\]\]><\/description>/,
        )?.[1] ??
        item.match(/<description>([\s\S]*?)<\/description>/)?.[1] ??
        null;
      const safeUrl = httpUrlOrNull(url);
      if (!title || !safeUrl) continue;
      posts.push({
        title: decodeEntities(title.trim()),
        url: safeUrl,
        date,
        // Substack wraps the standfirst in markup; strip tags and decode the handful of
        // entities that actually appear rather than pulling in an HTML parser.
        // Tags are stripped before entities are decoded, so a decoded "&lt;" cannot
        // become a tag that the strip already ran past.
        dek: rawDek
          ? decodeEntities(rawDek.replace(/<[^>]+>/g, ""))
              .replace(/\s+/g, " ")
              .trim() || null
          : null,
      });
      if (posts.length >= limit) break;
    }
    return posts;
  } catch {
    return [];
  }
}

export function formatDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatNumber(value: number | null, digits: number): string {
  if (value === null || Number.isNaN(value)) return "–";
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatSigned(value: number | null, digits: number): string {
  if (value === null || Number.isNaN(value)) return "";
  const body = Math.abs(value).toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (value === 0) return body;
  // A real minus sign, and always a sign — direction is never carried by colour alone.
  return `${value > 0 ? "+" : "−"}${body}`;
}
