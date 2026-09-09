"use client";

import { useMemo, useState } from "react";

import { TimeSeriesChart, type SeriesLine } from "@/components/charts/TimeSeriesChart";
import { SERIES_CYCLE } from "@/theme/plotly";

/**
 * A time-series chart a reader can narrow: window on the left, series on the right.
 *
 * The controls borrow the top navigation's idiom — small type, an ink underline on the
 * active item — rather than introducing buttons. A research page that grows a row of
 * pill buttons above every exhibit starts to read as an application; the point here is
 * that the controls recede until wanted.
 *
 * **Filtering happens on data already fetched.** The server sends the full window once,
 * and narrowing slices it in the browser, so changing the range is instant and costs no
 * request. The alternative — refetching per range — would put a network round trip
 * between a reader and a question they are asking of data already on the page.
 *
 * Series toggling duplicates what Plotly's own legend click does. It is here because a
 * legend entry gives no sign that it is clickable, and a reader who does not already
 * know the convention never discovers it.
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
  // Every point predates the cutoff: keep the line rather than empty it, so a series
  // that simply ended earlier -- serving.spreads stops in 2024 -- still draws instead of
  // vanishing when a reader picks a short window.
  if (from === -1) return line;
  return { ...line, x: line.x.slice(from), y: line.y.slice(from) };
}

const controlBase: React.CSSProperties = {
  background: "none",
  border: "none",
  padding: "0 0 2px",
  cursor: "pointer",
  fontFamily: "var(--body-stack)",
  fontSize: "var(--size-micro)",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  transition: "color var(--duration) var(--ease)",
};

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

  // Colours are pinned by each line's position in the *original* list, before any
  // filtering. TimeSeriesChart otherwise assigns them by index into what it receives, so
  // hiding the first series would recolour every remaining one -- and a reader who hides
  // a line to see the rest more clearly would find the rest had changed meaning.
  const coloured = useMemo(
    () =>
      lines.map((line, i) => ({
        ...line,
        color: line.color ?? SERIES_CYCLE[i % SERIES_CYCLE.length],
      })),
    [lines],
  );

  const shown = useMemo(() => {
    const cutoff = showRange ? cutoffFor(range) : null;
    return coloured
      .filter((line) => !hidden.has(line.name))
      .map((line) => withinRange(line, cutoff));
  }, [coloured, range, hidden, showRange]);

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

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "var(--space-3)",
          marginBottom: "var(--space-2)",
        }}
      >
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          {coloured.length > 1
            ? coloured.map((line) => {
                const isHidden = hidden.has(line.name);
                return (
                  <button
                    key={line.name}
                    type="button"
                    onClick={() => toggle(line.name)}
                    aria-pressed={!isHidden}
                    style={{
                      ...controlBase,
                      color: isHidden ? "var(--muted)" : "var(--text)",
                      textDecoration: isHidden ? "line-through" : "none",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                    }}
                  >
                    <span
                      aria-hidden
                      style={{
                        width: 9,
                        height: 2,
                        background: isHidden ? "var(--rule)" : line.color,
                        display: "inline-block",
                      }}
                    />
                    {line.name}
                  </button>
                );
              })
            : null}
        </div>

        {showRange ? (
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            {(Object.keys(RANGE_YEARS) as RangeKey[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setRange(key)}
                aria-pressed={range === key}
                style={{
                  ...controlBase,
                  color: range === key ? "var(--ink)" : "var(--muted)",
                  borderBottom:
                    range === key ? "1px solid var(--ink)" : "1px solid transparent",
                }}
              >
                {key}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <TimeSeriesChart
        lines={shown}
        unit={unit}
        secondaryUnit={secondaryUnit}
        height={height}
      />
    </div>
  );
}
