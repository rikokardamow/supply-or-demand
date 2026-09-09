/**
 * How old a source's **data** may be before a panel is greyed.
 *
 * Keyed by pipeline, not by table: Spec 32 §5 gives `seasonal` two thresholds — "8 days /
 * 2 days" — because WPSR and GIE both write it, and a per-table constant cannot express
 * that. `serving.publish_log` records which pipeline published, so the threshold follows
 * the pipeline whose rows the panel draws.
 *
 * **These are deliberately looser than Spec 32 §5's numbers, and looser than
 * `core/freshness.py`'s `EXPECTED_CADENCE_DAYS`.** Those measure *ingestion* age — time
 * since we last pulled successfully, against `revision_date`. Spec 33 §6 has the badge
 * read `as_of`, the data's own age, and every source publishes with a lag, so the same
 * number means different things on each side.
 *
 * Measured live 2026-09-09 against the real publish log, which is what settles it: the
 * *current* WPSR report (week ending 28 August, released Wednesday 3 September) is
 * already **12.6 days old** as data. Spec 32 §5's 8-day figure would have greyed the
 * flagship panel while it displayed the newest report EIA has published — a false alarm
 * on the one panel that must be trusted. GIE's own ~2-day lag has the same problem
 * against a 2-day threshold.
 *
 * So each threshold here is: publication cadence + the source's normal lag + a margin.
 */

const HOURS = 60 * 60 * 1000;
const DAYS = 24 * HOURS;

export const STALE_AFTER_MS: Record<string, number> = {
  // Weekly, reported for a week ending the Friday before release: the freshest possible
  // figure is already ~6 days old, and a week later it is ~13. Live check: 12.6 days and
  // current. 14 days flags a genuinely missed release without flagging a normal one.
  wpsr: 14 * DAYS,
  // Daily, published with a ~2-day lag. Live check: 2.6 days and current.
  gie: 4 * DAYS,
  // Dominated by hourly RTO interchange. Live check: 0.6 days.
  flows: 4 * DAYS,
  // Daily settles once a real source exists. Today this correctly reads stale: the
  // Barchart curve is a one-off 2026-09-04 snapshot, and serving.spreads' EIA source was
  // discontinued in April 2024 -- 887 days old, which is the finding, not a bug.
  curve: 4 * DAYS,
  // Every trading day; 4 days covers a long weekend plus a public holiday.
  yfinance: 4 * DAYS,
  // Weekly on a Friday; 10 days covers a public holiday without a false alarm.
  baker_hughes: 10 * DAYS,
  // The Petroleum Supply Monthly, published about two months behind the month it
  // reports. `/supply` was already calling isStale("eia", ...) with no entry here, so
  // those panels could never grey however far behind the release fell -- a staleness
  // check that cannot fire is worse than none, because it looks like one that passed.
  eia: 100 * DAYS,
  // Both are parsed from monthly publications, and OPEC's MOMR lands around the 11th-14th
  // -- so a month-old figure is normal and only two months is genuinely late.
  opec_momr: 60 * DAYS,
  jodi: 75 * DAYS,
  // Every derived series is only as fresh as the source beneath it; the daily moving
  // averages are the tightest of them.
  derived: 4 * DAYS,
  // GDELT and the social pulls run daily; OFAC's own SDN file is republished daily.
  events: 4 * DAYS,
  ofac: 4 * DAYS,
  // Near-real-time sources, unchanged from Spec 32 §5 -- neither publishes with a lag.
  // Spec 32 §5 sets 30 minutes: a position fix that old is no longer where the ship is.
  ais: 30 * 60 * 1000,
  grp: 26 * HOURS,
};

/**
 * When each source next publishes, in its own words.
 *
 * A figure dated 28 August on a page loaded on 9 September looks neglected, and there is
 * nothing on the page to say otherwise. It is not neglected: that *is* the newest week
 * EIA has released, and the next one is delayed to Thursday 10 September because Labor
 * Day fell on the 7th (confirmed against EIA's own release schedule on 2026-09-09).
 *
 * So each source states its cadence rather than a predicted date. A predicted date would
 * mean modelling US federal holidays, Ramadan-shifted OPEC publication and JODI's rolling
 * submission window — and the first time the model was wrong it would be a false claim
 * printed next to a real figure. A cadence is always true.
 */
export const RELEASE_CADENCE: Record<string, string> = {
  wpsr: "Weekly · Wed 10:30 ET, a day later after a Monday holiday",
  gie: "Daily · ~19:30 CET, for the previous gas day",
  flows: "Hourly to monthly, by source",
  curve: "Daily settles",
  yfinance: "Every trading day",
  baker_hughes: "Weekly · Fri ~noon CT",
  eia: "Monthly · about two months behind the reported month",
  opec_momr: "Monthly · around the 11th–14th",
  jodi: "Monthly · around the 20th",
  derived: "Recomputed whenever its source publishes",
  events: "Daily",
  ofac: "Daily, when OFAC republishes the SDN file",
  ais: "Continuous",
  grp: "Daily",
};

/**
 * Whether a panel's data is older than its pipeline allows.
 *
 * Measured against `as_of` — the data's own as-of — never `published_at`. That
 * distinction is the whole point: a pipeline that republishes an unchanged lake every
 * night has a fresh `published_at` and stale data, which is exactly the case a staleness
 * badge exists to catch.
 *
 * An unknown pipeline returns `false` rather than defaulting to stale: greying a panel
 * whose cadence nobody has recorded would be a guess presented as a finding.
 */
export function isStale(
  pipeline: string | null | undefined,
  asOf: string | null | undefined,
  now: Date = new Date(),
): boolean {
  if (!pipeline || !asOf) return false;
  const threshold = STALE_AFTER_MS[pipeline];
  if (threshold === undefined) return false;

  const age = now.getTime() - new Date(asOf).getTime();
  return Number.isFinite(age) && age > threshold;
}
