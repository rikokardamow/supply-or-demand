import { servingClient } from "@/lib/supabase";

/**
 * The live figures the landing page draws on.
 *
 * They are read from the same published tables the dashboard serves, at request time.
 * Nothing on the page is a placeholder or a hard-coded number, which is the point — a
 * research site whose landing page invents its own statistics has undermined itself
 * before a reader reaches the second screen.
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
