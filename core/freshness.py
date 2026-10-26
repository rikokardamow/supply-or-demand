"""Expected-cadence freshness checking (Spec 13 Session B). Pure read-side logic
over the existing lake -- no new schema, no writes."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from core.storage import last_ts_by_source, read_sanctions_current

# Real per-source cadence, matching infra/run_scheduled.py::CADENCE_GROUPS this
# same session -- expected max days between successful pulls. "newsapi"
# deliberately excluded: Spec 16's own manual-only design means it's never
# expected to refresh on any schedule, so it would otherwise show perpetually red.
EXPECTED_CADENCE_DAYS: dict[str, int] = {
    # Daily group. "open_meteo" (bare, no "_forecast" suffix) is deliberately
    # excluded -- confirmed live it's pipelines/weather/pull_weather.py's own
    # one-off historical-backfill source name, never re-pulled on any schedule
    # (the daily entrypoint, pull_daily.py, writes "open_meteo_forecast" instead).
    "gie": 2,
    "entsog": 2,
    "entsoe": 2,
    "eirgrid": 2,
    "gridstatus": 2,
    "open_meteo_forecast": 2,
    "gdelt": 2,
    "guardian": 2,
    # Weekly group.
    "baker_hughes": 9,
    "fred": 9,
    "frankfurter": 9,
    "eurostat": 9,
    "adanos": 9,
    # Real gotcha, confirmed live: pipelines/eia/pull_wpsr.py (weekly Wed),
    # pull_gas_storage.py (weekly Thu), and pull_production_exports.py (monthly)
    # all write ts_long with the SAME source="eia" -- and pull_padd_flows.py
    # (monthly) writes flows with source="eia" too. There is no way to
    # disambiguate which of the four last ran from `source` alone -- their own
    # series_id values are raw EIA API codes (e.g. WCSSTUS1), not namespaced by
    # pipeline sub-purpose (confirmed live against the real lake, not assumed).
    # Using the tightest real sub-cadence (weekly) here fails safe for "has
    # anything EIA-side run recently" but can't catch one specific EIA sub-pull
    # going stale while the others keep running -- a known, accepted blind spot,
    # documented rather than silently hidden.
    "eia": 9,
    # Monthly group.
    "opec_momr": 35,
    "jodi": 35,
    # Eurostat publishes monthly gas about two months after the month; pulled by hand monthly.
    "eurostat_gas": 35,
    "coal": 35,
}

# The sanctions table has no `source` column (it's single-source, OFAC only) --
# its own synthetic freshness key, checked against `sanctions.last_seen` rather
# than any ts_long/flows/events column. `events.source == "ofac"` only advances
# when something new is actually listed that day (see pipelines/ofac/
# events_bridge.py) -- a healthy daily OFAC pull with nothing new to report would
# look falsely stale under that signal, so `sanctions.last_seen` (updated on
# every successful run regardless of new listings) is the real health signal.
SANCTIONS_FRESHNESS_KEY = "ofac_sanctions"
EXPECTED_CADENCE_DAYS[SANCTIONS_FRESHNESS_KEY] = 2

_STATUS_COLUMNS = ["dataset", "source", "last_seen", "days_stale", "status"]


def _status(days_stale: float, expected_days: int) -> str:
    if days_stale <= expected_days:
        return "green"
    if days_stale <= expected_days * 2:
        return "amber"
    return "red"


def _rows_for(dataset: str, ts_col: str, now: pd.Timestamp) -> list[dict[str, object]]:
    """One row per source with an expected cadence. The max-per-source is computed in
    DuckDB (core.storage.last_ts_by_source), not by reading the dataset into pandas and
    grouping -- this runs on every rerun of the app's home page, and the whole lake is
    far too much to pull through pandas for three timestamps."""
    rows: list[dict[str, object]] = []
    for record in last_ts_by_source(dataset, ts_col).to_dict("records"):
        source = str(record["source"])
        if source not in EXPECTED_CADENCE_DAYS:
            continue
        last_seen = pd.Timestamp(record["last_seen"])
        days_stale = (now - last_seen).total_seconds() / 86400
        rows.append(
            {
                "dataset": dataset,
                "source": source,
                "last_seen": last_seen,
                "days_stale": round(days_stale, 1),
                "status": _status(days_stale, EXPECTED_CADENCE_DAYS[source]),
            }
        )
    return rows


def staleness_report() -> pd.DataFrame:
    """One row per (dataset, source) pair with an expected cadence -- last_seen,
    days_stale, status (green/amber/red). A source not in EXPECTED_CADENCE_DAYS
    (e.g. "newsapi", deliberately manual-only) is excluded rather than shown as
    perpetually red.

    `ts_long` uses `revision_date` (when the row was actually ingested), not
    `ts` (the data's own timestamp) -- confirmed live this matters, not just in
    theory: `open_meteo_forecast`'s `ts` values are genuinely in the future (a
    16-day weather forecast) and `opec_momr`'s can be too, so grouping by `ts`
    produced an impossible *negative* days_stale for both. `revision_date` is
    always the real ingestion time regardless of what period the data itself
    describes. `flows`/`events` have no revision_date column at all (per
    core/schemas.py), so `ts` is the only signal available there -- a reasonable
    proxy since neither carries forecast-dated rows the way ts_long does."""
    now = pd.Timestamp(datetime.now(UTC)).tz_localize(None)

    rows: list[dict[str, object]] = []
    rows += _rows_for("ts_long", "revision_date", now)
    rows += _rows_for("flows", "ts", now)
    rows += _rows_for("events", "ts", now)

    sanctions = read_sanctions_current()
    if not sanctions.empty:
        last_seen = pd.Timestamp(sanctions["last_seen"].max())
        days_stale = (now - last_seen).total_seconds() / 86400
        rows.append(
            {
                "dataset": "sanctions",
                "source": SANCTIONS_FRESHNESS_KEY,
                "last_seen": last_seen,
                "days_stale": round(days_stale, 1),
                "status": _status(days_stale, EXPECTED_CADENCE_DAYS[SANCTIONS_FRESHNESS_KEY]),
            }
        )

    return pd.DataFrame(rows, columns=_STATUS_COLUMNS)


# Fraction of every known source that must vanish at once before this is treated as
# a distinct, whole-lake incident rather than N unrelated single-pipeline staleness
# alerts. Calibrated against the real 2026-09-08 incident (an out-of-band event wiped
# data/lake/ and .venv/ together, cause never determined): every source went from
# "has data" to "zero rows anywhere" simultaneously, not one at a time on its own
# schedule -- staleness_report() alone can't tell that apart from a genuinely broken
# single pipeline, since a source with zero rows never appears in its output at all.
MASS_LOSS_FRACTION = 0.5


def missing_sources() -> set[str]:
    """Every `EXPECTED_CADENCE_DAYS` source with literally zero rows anywhere in the
    lake right now -- distinct from staleness, which only ever applies to a source
    that has written at least once. A source that has simply never been run yet looks
    identical to one that just lost all its history; this function can't tell those
    apart either, but `mass_data_loss_detected()` below cares about the aggregate
    count, not any single source's reason for being missing."""
    seen = set(staleness_report()["source"])
    return set(EXPECTED_CADENCE_DAYS) - seen


def mass_data_loss_detected(threshold: float = MASS_LOSS_FRACTION) -> bool:
    """True when more than `threshold` of every known source is simultaneously
    missing -- the real, confirmed-live signature of a whole-lake wipe. A single
    missing source (a pipeline never yet run, or one genuinely broken) must not trip
    this; only a large, simultaneous fraction should."""
    return len(missing_sources()) / len(EXPECTED_CADENCE_DAYS) > threshold
