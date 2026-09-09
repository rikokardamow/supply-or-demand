import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import { fetchEventCoverage, fetchRecentEvents } from "@/data/queries/events";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { isStale } from "@/data/staleness";
import { formatDate, formatNumber } from "@/lib/format";

/**
 * Events: tagged news, OFAC listings and self-hosted social sentiment.
 *
 * Severity is the field that decides whether an event ever reaches a price chart --
 * `event_overlay` on the Python side only draws severity >= 2 -- so it is shown here
 * rather than hidden, and the table is ordered newest first the way a wire is read.
 */
export const revalidate = 3600;

export default async function EventsPage() {
  const [recent, coverage, publish] = await Promise.all([
    fetchRecentEvents(120),
    fetchEventCoverage(),
    fetchLatestPublishBy("events", "events"),
  ]);

  const asOf = publish?.as_of ?? null;
  const stale = isStale("events", asOf);

  return (
    <>
      <PageHeader
        active="/events"
        title="Events"
        dek="Tagged news, OFAC listings and self-hosted social sentiment"
      />

      <main>
        <Panel
          title="Coverage by source"
          asOf={asOf}
          stale={stale}
          pipeline={"events"}
          sourceNote="Coverage rather than a volume chart, deliberately. OFAC's events all carry a single timestamp — the ingestion date, since a listing has no natural event time — so a daily-volume line would show one artificial spike dwarfing every real source. Distinct days is the honest measure of how much history each source actually spans."
        >
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.85rem",
              }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      ...cell,
                      textAlign: "left",
                      color: "var(--muted)",
                      fontSize: "0.72rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                    }}
                  >
                    Source
                  </th>
                  {[
                    "Events",
                    "Distinct days",
                    "Severity 2+",
                    "First",
                    "Last",
                  ].map((h) => (
                    <th
                      key={h}
                      style={{
                        ...cell,
                        textAlign: "right",
                        color: "var(--muted)",
                        fontSize: "0.72rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {coverage.map((c) => (
                  <tr key={c.source}>
                    <td style={cell}>{c.source}</td>
                    <td style={num}>{formatNumber(c.events, 0)}</td>
                    <td style={num}>{formatNumber(c.distinct_days, 0)}</td>
                    <td style={num}>{formatNumber(c.severity_2_plus, 0)}</td>
                    <td style={{ ...num, color: "var(--muted)" }}>
                      {formatDate(c.first_ts)}
                    </td>
                    <td style={{ ...num, color: "var(--muted)" }}>
                      {formatDate(c.last_ts)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="Most recent events"
          asOf={asOf}
          stale={stale}
          pipeline={"events"}
          sourceNote="Severity is the field that decides whether an event reaches a price chart: the Python overlay draws only severity 2 and above."
        >
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.85rem",
              }}
            >
              <thead>
                <tr>
                  {["Date", "Source", "Headline", "Commodity", "Severity"].map(
                    (h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: h === "Severity" ? "right" : "left",
                          padding: "0.4rem 0.6rem",
                          borderBottom: "1px solid var(--rule)",
                          fontSize: "0.72rem",
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                          color: "var(--muted)",
                        }}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {recent.map((e) => (
                  <tr key={e.event_id}>
                    <td style={cell}>{formatDate(e.ts)}</td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {e.source}
                    </td>
                    <td style={cell}>
                      {e.url ? (
                        <a
                          href={e.url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: "var(--ink)" }}
                        >
                          {e.headline}
                        </a>
                      ) : (
                        e.headline
                      )}
                    </td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {e.commodity ?? "–"}
                    </td>
                    <td
                      style={{
                        ...cell,
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {e.severity ?? "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </main>
    </>
  );
}

const cell: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid var(--rule)",
  verticalAlign: "top",
};

const num: React.CSSProperties = {
  ...cell,
  textAlign: "right",
  fontVariantNumeric: "tabular-nums",
};
