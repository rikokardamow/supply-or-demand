import { SeasonalChart } from "@/components/charts/SeasonalChart";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { Masthead } from "@/components/chrome/Masthead";
import { Panel } from "@/components/chrome/Panel";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { fetchSeasonalBand } from "@/data/queries/seasonal";
import { fetchSeries } from "@/data/queries/series";
import { isStale } from "@/data/staleness";
import { commonUnit, toLines } from "@/data/toLines";

/**
 * Gas (Spec 33.03): EU storage against its seasonal band, the injection path, LNG, and
 * the national breakdown.
 *
 * Every series here comes from GIE's AGSI+/ALSI+ pull, already in `serving.*` -- 142
 * series, so the constraint on this screen is what is worth showing rather than what is
 * available.
 */
export const revalidate = 3600;

const PIPELINE = "gie";

const FLOW_SERIES = {
  "agsi.EU.injection": "Injection",
  "agsi.EU.withdrawal": "Withdrawal",
};

const LNG_SERIES = {
  "alsi.EU.send_out": "LNG send-out",
  "alsi.EU.lng_inventory": "LNG inventory",
};

// The five largest EU storage systems by working gas volume. Chosen because they carry
// the volume, not alphabetically -- a chart of the five smallest would be honest and
// useless.
const COUNTRY_SERIES = {
  "agsi.DE.full_pct": "Germany",
  "agsi.IT.full_pct": "Italy",
  "agsi.NL.full_pct": "Netherlands",
  "agsi.FR.full_pct": "France",
  "agsi.AT.full_pct": "Austria",
};

export default async function GasPage() {
  const [euBand, deBand, flows, lng, countries, publish] = await Promise.all([
    fetchSeasonalBand("agsi.EU.full_pct"),
    fetchSeasonalBand("agsi.DE.full_pct"),
    fetchSeries(Object.keys(FLOW_SERIES), 3),
    fetchSeries(Object.keys(LNG_SERIES), 3),
    fetchSeries(Object.keys(COUNTRY_SERIES), 3),
    fetchLatestPublishBy("series_long", PIPELINE),
  ]);

  const stale = isStale(PIPELINE, publish?.as_of);
  const asOf = publish?.as_of ?? null;

  return (
    <main>
      <Masthead active="/gas" />

      <h2
        style={{
          fontFamily: "var(--heading-stack)",
          fontSize: "1.6rem",
          margin: "0.5rem 0 0.35rem",
        }}
      >
        Gas
      </h2>
      <p
        style={{ color: "var(--muted)", fontSize: "0.82rem", margin: "0 0 1.6rem" }}
      >
        GIE AGSI+ storage and ALSI+ LNG — EU aggregate and member countries
      </p>

      <Panel
        title="EU storage fullness against its seasonal range"
        asOf={asOf}
        stale={stale}
        sourceNote="Seven-year range and median, 2020 excluded. This year stops at the last reported gas day rather than running to year end."
      >
        <SeasonalChart
          rows={euBand}
          unit={euBand.find((r) => r.unit)?.unit ?? null}
          bandYears={euBand.find((r) => r.years)?.years ?? null}
        />
      </Panel>

      <Panel
        title="Germany storage fullness against its seasonal range"
        asOf={asOf}
        stale={stale}
        sourceNote="The largest single EU storage system, and the one the TTF curve trades against."
      >
        <SeasonalChart
          rows={deBand}
          unit={deBand.find((r) => r.unit)?.unit ?? null}
          bandYears={deBand.find((r) => r.years)?.years ?? null}
        />
      </Panel>

      <Panel
        title="Storage fullness by country"
        asOf={asOf}
        stale={stale}
        sourceNote="The five largest EU storage systems by working gas volume."
      >
        <TimeSeriesChart
          lines={toLines(countries, COUNTRY_SERIES)}
          unit={commonUnit(countries)}
        />
      </Panel>

      <Panel
        title="EU injection and withdrawal"
        asOf={asOf}
        stale={stale}
        sourceNote="Gross flows, not netted: both run simultaneously across a system this size, and netting them would hide the turnover."
      >
        <TimeSeriesChart lines={toLines(flows, FLOW_SERIES)} unit={commonUnit(flows)} />
      </Panel>

      <Panel
        title="EU LNG send-out and terminal inventory"
        asOf={asOf}
        stale={stale}
        sourceNote="Send-out is a daily rate (GWh/d); inventory is a stock (1000 m³), so the two sit on separate axes."
      >
        <TimeSeriesChart
          lines={toLines(lng, LNG_SERIES, { secondary: ["alsi.EU.lng_inventory"] })}
          unit="GWh/d"
          secondaryUnit="1000 m³"
        />
      </Panel>
    </main>
  );
}
