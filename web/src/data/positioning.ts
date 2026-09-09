import type { SeriesLine } from "@/components/charts/TimeSeriesChart";
import { bySeries } from "@/data/queries/series";
import type { SeriesLongRow } from "@/types/database";

/**
 * Derived Commitments of Traders measures, computed here rather than published.
 *
 * `pipelines/cftc` publishes what the CFTC actually reports — managed money long, managed
 * money short, producer/merchant long and short, and open interest. Net length is a
 * difference and share-of-open-interest is a ratio, and both are read-time transforms,
 * matching `pipelines/gie/transforms.py:net_flow`. Storing a difference alongside its own
 * two operands is how the three end up disagreeing.
 *
 * **Both measures are aligned on timestamp, not on position.** The four contracts share a
 * report date but Brent's history starts in 2011 and the NYMEX contracts' in 2006, and a
 * missing week in one leg would silently pair the wrong two numbers if these were zipped
 * by index. A date present in one leg and not the other yields no point at all.
 */

/**
 * The four contracts, named as the CFTC names them.
 *
 * **"Brent" here is NYMEX Brent Last Day (BZ), not ICE Brent.** Confirmed against the
 * CFTC's own `market_and_exchange_names` on 2026-09-09: code 06765T returns "BRENT LAST
 * DAY - NEW YORK MERCANTILE EXCHANGE". The CFTC only receives reports from
 * US-regulated exchanges, and ICE Brent — the contract everyone means by "Brent" — trades
 * on ICE Futures Europe and reports to the FCA instead. Its COT-equivalent is in ICE's own
 * Commitments of Traders, which this pipeline does not pull.
 *
 * That difference is not cosmetic: BZ's managed money net is a fraction of ICE Brent's, so
 * a chart labelled plainly "Brent" would have a reader comparing a number against a
 * benchmark it is not measuring. Every label carries its exchange for that reason.
 */
export const CONTRACTS = {
  cl: { label: "WTI", market: "WTI Physical · NYMEX" },
  lco: {
    label: "Brent (BZ)",
    market: "Brent Last Day · NYMEX — not ICE Brent",
  },
  rb: { label: "RBOB", market: "Gasoline RBOB · NYMEX" },
  ho: { label: "ULSD", market: "NY Harbor ULSD · NYMEX" },
} as const;

export type Root = keyof typeof CONTRACTS;

export const POSITIONING_SERIES = Object.keys(CONTRACTS).flatMap((root) => [
  `cftc.${root}.mm_long`,
  `cftc.${root}.mm_short`,
  `cftc.${root}.oi`,
]);

/** Pair two series on their shared timestamps and combine them point by point. */
function combine(
  rows: SeriesLongRow[],
  leftId: string,
  rightId: string,
  f: (left: number, right: number) => number | null,
): { x: string[]; y: (number | null)[] } {
  const grouped = bySeries(rows);
  const right = new Map(
    (grouped.get(rightId) ?? []).map((r) => [r.ts, r.value] as const),
  );

  const x: string[] = [];
  const y: (number | null)[] = [];
  for (const point of grouped.get(leftId) ?? []) {
    const other = right.get(point.ts);
    if (point.value === null || other === null || other === undefined) continue;
    x.push(point.ts);
    y.push(f(point.value, other));
  }
  return { x, y };
}

/**
 * Managed money net length, in contracts: long minus short.
 *
 * The number the trade actually quotes. A fund that is 300,000 long and 100,000 short is
 * not "300,000 long" in any sense that matters to price, and reporting the gross leg
 * alone overstates conviction by however large the other leg happens to be.
 */
export function netLengthLines(rows: SeriesLongRow[]): SeriesLine[] {
  return Object.entries(CONTRACTS).flatMap(([root, { label }]) => {
    const { x, y } = combine(
      rows,
      `cftc.${root}.mm_long`,
      `cftc.${root}.mm_short`,
      (long, short) => long - short,
    );
    return x.length === 0 ? [] : [{ name: label, x, y }];
  });
}

/**
 * Managed money net length as a share of open interest, in per cent.
 *
 * Contracts are not comparable across markets — WTI's open interest dwarfs heating oil's,
 * so a net figure in lots says more about the size of the contract than about how
 * stretched positioning is. As a share of the open interest it sits in, the four become
 * one chart a reader can actually compare down.
 */
export function netShareLines(rows: SeriesLongRow[]): SeriesLine[] {
  const grouped = bySeries(rows);

  return Object.entries(CONTRACTS).flatMap(([root, { label }]) => {
    const oi = new Map(
      (grouped.get(`cftc.${root}.oi`) ?? []).map(
        (r) => [r.ts, r.value] as const,
      ),
    );
    const { x, y } = combine(
      rows,
      `cftc.${root}.mm_long`,
      `cftc.${root}.mm_short`,
      (long, short) => long - short,
    );

    const share = y.map((net, i) => {
      const open = oi.get(x[i]);
      // A week with no open interest reported, or a genuine zero, has no share. Dividing
      // would give an infinity that renders as a real spike.
      if (net === null || open === null || open === undefined || open === 0)
        return null;
      return (net / open) * 100;
    });

    return x.length === 0 ? [] : [{ name: label, x, y: share }];
  });
}

/** One contract's two managed-money legs, for a page that shows the gross detail. */
export function legLines(rows: SeriesLongRow[], root: Root): SeriesLine[] {
  const grouped = bySeries(rows);
  return [
    { id: `cftc.${root}.mm_long`, name: "Managed money long" },
    { id: `cftc.${root}.mm_short`, name: "Managed money short" },
    { id: `cftc.${root}.oi`, name: "Open interest" },
  ].flatMap(({ id, name }) => {
    const points = grouped.get(id);
    if (!points || points.length === 0) return [];
    return [
      { name, x: points.map((p) => p.ts), y: points.map((p) => p.value) },
    ];
  });
}
