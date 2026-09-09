import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { Panel } from "@/components/chrome/Panel";
import { toLines } from "@/data/toLines";
import { formatNumber } from "@/lib/format";
import { SERIES } from "@/theme/plotly";
import type { SeasonalRow, SeriesLongRow } from "@/types/database";

/**
 * One ticker's two exhibits: price against its moving averages, and price against its
 * own seasonal range.
 *
 * The moving averages are read from `derived.ma.<root>.<window>`, computed by
 * `pipelines/derived/moving_averages.py` — not recalculated here. A figure quoted in an
 * article and the line on this chart come from the same published rows.
 *
 * The three windows share one colour ramp from navy outwards rather than taking the
 * default palette: they are the same quantity at three speeds, and giving the 200-day a
 * colour that reads as a different series would misstate that.
 */

const MA_STYLE: Record<number, { color: string; dash: "solid" | "dot" | "dash" }> = {
  50: { color: SERIES.lightBlue, dash: "solid" },
  100: { color: SERIES.orange, dash: "dash" },
  200: { color: SERIES.red, dash: "dot" },
};

export const MA_WINDOWS = [50, 100, 200] as const;

export function maSeriesId(root: string, window: number): string {
  return `derived.ma.${root}.${window}`;
}

export function TickerPanels({
  root,
  label,
  unit,
  price,
  band,
  asOf,
  stale,
}: {
  root: string;
  label: string;
  unit: string | null;
  price: SeriesLongRow[];
  band: SeasonalRow[];
  asOf: string | null;
  stale: boolean;
}) {
  const closeId = `fut.${root}.f01.close`;
  const latest = price.filter((r) => r.series_id === closeId).at(-1)?.value ?? null;

  const labels: Record<string, string> = { [closeId]: "Close" };
  for (const window of MA_WINDOWS) {
    labels[maSeriesId(root, window)] = `${window}-day`;
  }

  const lines = toLines(price, labels).map((line) => {
    const window = MA_WINDOWS.find((w) => line.name === `${w}-day`);
    if (!window) return { ...line, color: SERIES.navy };
    return { ...line, ...MA_STYLE[window] };
  });

  return (
    <>
      <Panel
        title={`${label} — close and moving averages`}
        asOf={asOf}
        stale={stale}
        sourceNote={
          `Simple moving averages over 50, 100 and 200 trading sessions, computed in ` +
          `pipelines/derived/moving_averages.py. Each line starts only once its window ` +
          `is genuinely full, so a 200-day average begins 200 sessions in rather than ` +
          `creeping up from a shorter one.` +
          (latest !== null ? ` Latest close ${formatNumber(latest, 2)} ${unit ?? ""}.` : "")
        }
      >
        <TimeSeriesChart lines={lines} unit={unit} height={340} />
      </Panel>

      <Panel
        title={`${label} — seasonal range`}
        asOf={asOf}
        stale={stale}
        sourceNote="Seven-year range and median by day of year, 2020 excluded. This year's track stops at the last close rather than running to year end."
      >
        {band.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>No seasonal band published.</p>
        ) : (
          <SeasonalChart
            rows={band}
            unit={band.find((r) => r.unit)?.unit ?? unit}
            bandYears={band.find((r) => r.years)?.years ?? null}
          />
        )}
      </Panel>
    </>
  );
}
