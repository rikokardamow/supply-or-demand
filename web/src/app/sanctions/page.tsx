import { PageHeader } from "@/components/chrome/PageHeader";
import { Panel } from "@/components/chrome/Panel";
import {
  fetchFlagCounts,
  fetchProgrammeCounts,
  fetchSanctionTotals,
  fetchSanctionedVessels,
} from "@/data/queries/events";
import type { LabelCount } from "@/data/queries/events";
import { fetchLatestPublishBy } from "@/data/queries/publishLog";
import { isStale } from "@/data/staleness";
import { formatDate, formatNumber } from "@/lib/format";

/**
 * Sanctions: the OFAC Specially Designated Nationals list, and the ships on it.
 *
 * **These vessels are identities, not positions.** OFAC gives a listed ship's name, IMO,
 * flag, owner and call sign; it says nothing about where that ship is. This project has
 * no AIS feed at all — Spec 11 is unbuilt and the lake holds no vessel position — so
 * this screen deliberately shows a register and never a map. Presenting it as vessel
 * tracking would be a claim the data cannot support.
 */
export const revalidate = 3600;

const cell: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
};

const head: React.CSSProperties = {
  ...cell,
  textAlign: "left",
  fontSize: "0.72rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--muted)",
};

export default async function SanctionsPage() {
  const [vessels, totals, flags, programmes, publish] = await Promise.all([
    fetchSanctionedVessels(150),
    fetchSanctionTotals(),
    fetchFlagCounts(12),
    fetchProgrammeCounts(12),
    fetchLatestPublishBy("sanctions", "ofac"),
  ]);

  const asOf = publish?.as_of ?? null;
  const stale = isStale("ofac", asOf);

  return (
    <>
      <PageHeader
        active="/sanctions"
        title="Sanctions"
        dek={
          <>
            OFAC Specially Designated Nationals —{" "}
            {formatNumber(totals.entries, 0)} listed entries, of which{" "}
            {formatNumber(totals.energy_related, 0)} are energy-related and{" "}
            {formatNumber(totals.with_imo, 0)} carry a vessel IMO number
          </>
        }
      />

      <main>
        <Panel
          title="Sanctioned vessels"
          asOf={asOf}
          stale={stale}
          pipeline={"ofac"}
          sourceNote="A register, not a tracker. OFAC identifies a listed ship by name, IMO, flag and owner; it carries no position, and this project has no AIS feed, so nothing here says where a vessel is."
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
                  {["Vessel", "Type", "Flag", "Owner", "IMO", "Listed"].map(
                    (h) => (
                      <th key={h} style={head}>
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {vessels.map((v) => (
                  <tr key={v.sanction_id}>
                    <td style={cell}>{v.name}</td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {v.vess_type ?? "–"}
                    </td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {v.vess_flag ?? "–"}
                    </td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {v.vess_owner ?? "–"}
                    </td>
                    <td style={{ ...cell, fontVariantNumeric: "tabular-nums" }}>
                      {v.imo}
                    </td>
                    <td style={{ ...cell, color: "var(--muted)" }}>
                      {formatDate(v.first_seen)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="Vessel flags most represented"
          asOf={asOf}
          stale={stale}
          pipeline={"ofac"}
          sourceNote="Flags of convenience dominate by construction: a flag appearing often here reflects where sanctioned tonnage registers, not any judgement about the registry itself."
        >
          <FrequencyTable rows={flags} label="Flag" />
        </Panel>

        <Panel
          title="Sanctions programmes"
          asOf={asOf}
          stale={stale}
          pipeline={"ofac"}
          sourceNote="An entry can sit under several programmes at once; these are the programme strings exactly as OFAC publishes them, uncombined."
        >
          <FrequencyTable rows={programmes} label="Programme" />
        </Panel>
      </main>
    </>
  );
}

function FrequencyTable({
  rows,
  label,
}: {
  rows: LabelCount[];
  label: string;
}) {
  const max = rows[0]?.entries ?? 1;
  return (
    <table
      style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}
    >
      <thead>
        <tr>
          <th style={head}>{label}</th>
          <th style={{ ...head, textAlign: "right" }}>Entries</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ label: name, entries: count }) => (
          <tr key={name}>
            <td style={cell}>{name}</td>
            <td
              style={{
                ...cell,
                textAlign: "right",
                fontVariantNumeric: "tabular-nums",
                // A wash proportional to the count, so the shape of the distribution is
                // readable without a second chart.
                background: `linear-gradient(to left, rgba(15,42,74,0.12) ${(100 * count) / max}%, transparent ${(100 * count) / max}%)`,
              }}
            >
              {formatNumber(count, 0)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
