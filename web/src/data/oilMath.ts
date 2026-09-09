import type { SeriesLine } from "@/components/charts/TimeSeriesChart";
import { bySeries } from "@/data/queries/series";
import type { SeriesLongRow } from "@/types/database";

/**
 * The weekly US crude balance, and the measures that fall out of it.
 *
 * Every figure here is EIA's Weekly Petroleum Status Report, already in
 * `serving.series_long`. Nothing is published for this screen -- these are all read-time
 * transforms of series the lake already holds, the same call
 * `pipelines/gie/transforms.py:net_flow` makes for storage flows.
 *
 * **Units.** Flows are thousand barrels per day (MBBL/D); stocks are thousand barrels
 * (MBBL). A weekly stock change therefore has to be divided by seven before it can be
 * compared with a flow, and every function here that mixes the two does so explicitly.
 */

export const BALANCE_SERIES = [
  "WCRFPUS2", // crude production, MBBL/D
  "WCEIMUS2", // crude imports, MBBL/D
  "WCREXUS2", // crude exports, MBBL/D
  "WCRRIUS2", // refiner net input of crude, MBBL/D
  "WCESTUS1", // commercial crude stocks excluding SPR, MBBL
  "WCSSTUS1", // Strategic Petroleum Reserve, MBBL
  "WPULEUS3", // refinery utilisation, %
  "WGIRIUS2", // refinery gross inputs, MBBL/D
  "WRPUPUS2", // total products supplied, MBBL/D
  "WGFUPUS2", // motor gasoline supplied, MBBL/D
  "WDIUPUS2", // distillate supplied, MBBL/D
];

export const CRACK_SERIES = {
  "derived.crack.us321.spot": "US 3-2-1",
  "derived.crack.nyh_gasoline.spot": "NY Harbor gasoline",
  "derived.crack.nyh_distillate.spot": "NY Harbor distillate",
  "derived.crack.gulf321.spot": "Gulf Coast 3-2-1",
};

const DAYS_PER_WEEK = 7;

type Wide = Map<string, Map<string, number>>;

/** Pivot flat rows into `series_id -> ts -> value`, and the sorted date axis. */
function pivot(rows: SeriesLongRow[]): { wide: Wide; dates: string[] } {
  const grouped = bySeries(rows);
  const wide: Wide = new Map();
  const dates = new Set<string>();

  for (const [seriesId, points] of grouped) {
    const byDate = new Map<string, number>();
    for (const p of points) {
      if (p.value === null || p.value === undefined) continue;
      byDate.set(p.ts, p.value);
      dates.add(p.ts);
    }
    wide.set(seriesId, byDate);
  }
  return { wide, dates: [...dates].sort() };
}

export type BalanceWeek = {
  ts: string;
  production: number | null;
  imports: number | null;
  exports: number | null;
  runs: number | null;
  /** Production + imports − exports − runs, in MBBL/D. */
  implied: number | null;
  /** The actual change in total crude stocks (commercial + SPR), in MBBL/D. */
  actual: number | null;
  /** Actual − implied: EIA's own crude adjustment, the barrels the identity cannot place. */
  adjustment: number | null;
};

/**
 * The crude balance, week by week.
 *
 * The identity is
 *
 *     Δ(commercial + SPR stocks) = production + imports − exports − refinery runs + adjustment
 *
 * and **the adjustment is not a rounding error**. EIA publishes it as a line of its own
 * because the components are collected from different surveys with different coverage, and
 * since about 2015 it has run persistently positive at several hundred thousand barrels a
 * day. Verified against the published data on 2026-09-09: for the twelve weeks to 28
 * August the residual computed here ran −242 to +915 MBBL/D, which is the magnitude and
 * sign EIA's own adjustment carries.
 *
 * **The SPR is on the left-hand side, not omitted.** A release moves barrels out of the
 * reserve and into commercial tanks; leaving it out would charge the whole transfer to the
 * adjustment and make the identity look far more broken than it is. Confirmed on the same
 * data: the latest week's release of 446 MBBL/D accounts for most of the gap between an
 * implied draw of 1,347 and a commercial draw of 636.
 */
export function crudeBalance(rows: SeriesLongRow[]): BalanceWeek[] {
  const { wide, dates } = pivot(rows);
  const at = (id: string, ts: string) => wide.get(id)?.get(ts) ?? null;

  return dates.map((ts, i) => {
    const production = at("WCRFPUS2", ts);
    const imports = at("WCEIMUS2", ts);
    const exports = at("WCREXUS2", ts);
    const runs = at("WCRRIUS2", ts);

    const implied =
      production === null || imports === null || exports === null || runs === null
        ? null
        : production + imports - exports - runs;

    // A stock change needs the previous week, so the first row has none. Reaching back by
    // index is safe here because `dates` is the sorted union across every series and every
    // WPSR week appears in all of them.
    const previous = i === 0 ? null : dates[i - 1];
    const commNow = at("WCESTUS1", ts);
    const commWas = previous === null ? null : at("WCESTUS1", previous);
    const sprNow = at("WCSSTUS1", ts);
    const sprWas = previous === null ? null : at("WCSSTUS1", previous);

    const actual =
      commNow === null || commWas === null || sprNow === null || sprWas === null
        ? null
        : (commNow - commWas + (sprNow - sprWas)) / DAYS_PER_WEEK;

    return {
      ts,
      production,
      imports,
      exports,
      runs,
      implied,
      actual,
      adjustment: actual === null || implied === null ? null : actual - implied,
    };
  });
}

/** The balance components as signed contributions: what adds to stocks and what draws. */
export function balanceComponentLines(weeks: BalanceWeek[]): SeriesLine[] {
  const x = weeks.map((w) => w.ts);
  return [
    { name: "Production", y: weeks.map((w) => w.production) },
    { name: "Imports", y: weeks.map((w) => w.imports) },
    // Negated: exports and refinery runs remove barrels from the crude pool. The sign is
    // the point of the chart -- stacked against production and imports, the gap between
    // the two sides is the build or draw.
    { name: "Exports", y: weeks.map((w) => (w.exports === null ? null : -w.exports)) },
    { name: "Refinery runs", y: weeks.map((w) => (w.runs === null ? null : -w.runs)) },
  ].map((line) => ({ ...line, x }));
}

/** Implied build against the reported one, and the adjustment between them. */
export function balanceCheckLines(weeks: BalanceWeek[]): SeriesLine[] {
  const x = weeks.map((w) => w.ts);
  return [
    { name: "Implied by the components", x, y: weeks.map((w) => w.implied) },
    { name: "Reported stock change", x, y: weeks.map((w) => w.actual) },
    { name: "EIA adjustment", x, y: weeks.map((w) => w.adjustment) },
  ];
}

/**
 * Days of cover: crude stocks divided by the rate refineries are consuming them.
 *
 * The headline stock measure, ahead of the barrel count. An absolute level drifts with
 * structural growth in refining capacity, so 400 million barrels in 1990 and in 2026 are
 * not the same degree of comfort; dividing by current runs normalises for it and gives a
 * figure that is comparable through time. This follows the MOMR's own convention of
 * reporting OECD stocks in days of forward cover alongside the level.
 *
 * Commercial stocks only. The SPR is not available to refiners on a weekly basis, so
 * including it would overstate cover by roughly a fortnight.
 */
export function daysOfCoverLine(rows: SeriesLongRow[]): SeriesLine[] {
  const { wide, dates } = pivot(rows);
  const stocks = wide.get("WCESTUS1");
  const runs = wide.get("WCRRIUS2");
  if (!stocks || !runs) return [];

  return [
    {
      name: "Days of cover",
      x: dates,
      y: dates.map((ts) => {
        const s = stocks.get(ts);
        const r = runs.get(ts);
        // A week with no reported runs, or a genuine zero, has no cover figure. Dividing
        // would give an infinity that renders as a real spike.
        if (s === undefined || r === undefined || r === 0) return null;
        return s / r;
      }),
    },
  ];
}

/** Two named series against a shared date axis, breaking where either is missing. */
export function pairLines(
  rows: SeriesLongRow[],
  spec: { id: string; name: string; secondary?: boolean }[],
): SeriesLine[] {
  const { wide, dates } = pivot(rows);
  return spec.flatMap(({ id, name, secondary }) => {
    const byDate = wide.get(id);
    if (!byDate || byDate.size === 0) return [];
    return [
      {
        name,
        x: dates,
        y: dates.map((ts) => byDate.get(ts) ?? null),
        secondary,
      },
    ];
  });
}
