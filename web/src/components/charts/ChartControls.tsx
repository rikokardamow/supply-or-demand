"use client";

import { useMemo, useState } from "react";

import {
  TimeSeriesChart,
  type SeriesLine,
} from "@/components/charts/TimeSeriesChart";
import { SERIES_CYCLE } from "@/theme/plotly";

/**
 * A time-series chart a reader can narrow: series chips on the left, a segmented range
 * control on the right.
 *
 * **Filtering happens on data already fetched.** The server sends the full window once,
 * and narrowing slices it in the browser, so changing the range is instant and costs no
 * request.
 *
 * Series toggling duplicates what Plotly's own legend click does. It is here because a
 * legend entry gives no sign that it is clickable, and a reader who does not already know
 * the convention never discovers it — so `TimeSeriesChart` draws no legend of its own
 * wherever these chips appear.
 */

export type RangeKey = "1Y" | "5Y" | "Max";

const RANGE_YEARS: Record<RangeKey, number | null> = {
  "1Y": 1,
  "5Y": 5,
  Max: null,
};

function cutoffFor(range: RangeKey): Date | null {
  const years = RANGE_YEARS[range];
  if (years === null) return null;
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - years);
  return cutoff;
}

/** Slice a line to points on or after `cutoff`, keeping x and y aligned. */
function withinRange(line: SeriesLine, cutoff: Date | null): SeriesLine {
  if (cutoff === null) return line;
  const from = line.x.findIndex((x) => new Date(x) >= cutoff);
  // Every point predates the cutoff: keep the line rather than empty it, so a series that
  // simply ended earlier -- serving.spreads stops in 2024 -- still draws instead of
  // vanishing when a reader picks a short window.
  if (from === -1) return line;
  return { ...line, x: line.x.slice(from), y: line.y.slice(from) };
}

/** How many years of data are actually on the page, across all series. */
function spanYears(lines: SeriesLine[]): number {
  let earliest = Infinity;
  for (const line of lines) {
    const first = line.x[0];
    if (first === undefined) continue;
    const t = new Date(first).getTime();
    if (Number.isFinite(t) && t < earliest) earliest = t;
  }
  if (!Number.isFinite(earliest)) return 0;
  return (Date.now() - earliest) / (365.25 * 24 * 60 * 60 * 1000);
}

export function ChartControls({
  lines,
  unit,
  secondaryUnit,
  height,
  defaultRange = "5Y",
  showRange = true,
}: {
  lines: SeriesLine[];
  unit?: string | null;
  secondaryUnit?: string | null;
  height?: number;
  defaultRange?: RangeKey;
  /** Off for a categorical x-axis — a forward curve has no time window to narrow. */
  showRange?: boolean;
}) {
  const [range, setRange] = useState<RangeKey>(defaultRange);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());

  // Colours and line weights are pinned by each line's position in the *original* list,
  // before any filtering. TimeSeriesChart otherwise assigns both by index into what it
  // receives, so hiding the first series would recolour every remaining one and promote
  // whichever line landed at index 0 to the bold "primary" weight -- a reader who hid a
  // line to see the rest more clearly would find the rest had changed meaning.
  const coloured = useMemo(
    () =>
      lines.map((line, i) => ({
        ...line,
        color: line.color ?? SERIES_CYCLE[i % SERIES_CYCLE.length],
        width: line.width ?? (i === 0 ? 2 : 1.5),
      })),
    [lines],
  );

  // Only offer windows the data can actually fill. A three-year series behind a "5Y" and a
  // "Max" button renders both identically, so two of the three controls silently claim to
  // do something they do not -- and "Max" stops meaning maximum. A window is offered only
  // when there is more history than it shows.
  const ranges = useMemo(() => {
    const span = spanYears(coloured);
    const offered = (Object.keys(RANGE_YEARS) as RangeKey[]).filter((key) => {
      const years = RANGE_YEARS[key];
      return years === null || years < span;
    });
    return offered.length > 1 ? offered : [];
  }, [coloured]);

  const effectiveRange = ranges.includes(range) ? range : "Max";

  const shown = useMemo(() => {
    const cutoff = showRange ? cutoffFor(effectiveRange) : null;
    return coloured
      .filter((line) => !hidden.has(line.name))
      .map((line) => withinRange(line, cutoff));
  }, [coloured, effectiveRange, hidden, showRange]);

  function toggle(name: string) {
    setHidden((current) => {
      const next = new Set(current);
      // Never hide the last visible series: an empty chart looks like missing data, and
      // the reader has no way to tell it apart from a failed query.
      if (next.has(name)) next.delete(name);
      else if (lines.length - next.size > 1) next.add(name);
      return next;
    });
  }

  const showChips = coloured.length > 1;
  const showSegments = showRange && ranges.length > 0;

  return (
    <div>
      {showChips || showSegments ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "var(--space-3)",
            marginBottom: "var(--space-4)",
          }}
        >
          <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            {showChips
              ? coloured.map((line) => {
                  const isHidden = hidden.has(line.name);
                  return (
                    <button
                      key={line.name}
                      type="button"
                      className="term-key term-key--series"
                      onClick={() => toggle(line.name)}
                      aria-pressed={!isHidden}
                    >
                      <span
                        aria-hidden
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: 2,
                          background: isHidden
                            ? "var(--border-strong)"
                            : line.color,
                          display: "inline-block",
                        }}
                      />
                      {line.name}
                    </button>
                  );
                })
              : null}
          </div>

          {showSegments ? (
            <div style={{ display: "flex", gap: 0 }}>
              {ranges.map((key) => (
                <button
                  key={key}
                  type="button"
                  className="term-key term-key--range"
                  onClick={() => setRange(key)}
                  aria-pressed={effectiveRange === key}
                >
                  {key}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <TimeSeriesChart
        lines={shown}
        unit={unit}
        secondaryUnit={secondaryUnit}
        height={height}
        showLegend={!showChips}
      />
    </div>
  );
}
