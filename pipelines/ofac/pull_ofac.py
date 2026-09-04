"""Daily entrypoint: fetches the current OFAC SDN snapshot, tags it (energy
relevance, IMO, geo), diffs it against the existing rolling state
(first_seen/last_seen/status), writes both the rolling "current" table and a
dated raw-snapshot audit archive, then bridges newly-listed energy-related rows
into the existing `events` lake (Spec 09) -- see
pipelines/ofac/events_bridge.py."""

from __future__ import annotations

import pandas as pd
from core.storage import (
    read_sanctions_current,
    write_events,
    write_sanctions_current,
    write_sanctions_snapshot,
)
from pipelines.ofac.client import fetch_sdn_csv
from pipelines.ofac.events_bridge import sanctions_to_events
from pipelines.ofac.tagging import extract_imo, is_energy_related, resolve_geo


def tag_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["imo"] = df["remarks"].map(extract_imo)
    df["energy_related"] = df.apply(
        lambda row: is_energy_related(
            row["name"], row["remarks"], row["programs"], row["entity_type"]
        ),
        axis=1,
    )
    return df


def compute_diff(
    previous: pd.DataFrame, current_tagged: pd.DataFrame, pull_date: pd.Timestamp
) -> pd.DataFrame:
    """`current_tagged` rows get status="active", last_seen=pull_date, and
    first_seen preserved from `previous` when the sanction_id was already there
    (else pull_date -- genuinely new). Rows in `previous` but absent from
    `current_tagged` get status="delisted" with first_seen/last_seen left
    UNCHANGED -- the last date they were actually seen, not today's pull date,
    per specs/15_ofac-sanctions.md's own wording."""
    current = current_tagged.copy()
    current["status"] = "active"
    current["last_seen"] = pull_date

    if previous.empty:
        current["first_seen"] = pull_date
    else:
        first_seen_by_id = previous.set_index("sanction_id")["first_seen"].to_dict()
        current["first_seen"] = current["sanction_id"].map(
            lambda sid: first_seen_by_id.get(sid, pull_date)
        )

    if previous.empty:
        return current

    current_ids = set(current["sanction_id"])
    delisted = previous[~previous["sanction_id"].isin(current_ids)].copy()
    delisted["status"] = "delisted"

    return pd.concat([current, delisted], ignore_index=True)


def main() -> None:
    pull_date = pd.Timestamp.now(tz="UTC").tz_localize(None)

    raw = fetch_sdn_csv()
    print(f"ofac: fetched {len(raw)} raw rows", flush=True)

    tagged = tag_snapshot(raw)
    tagged["geo"] = tagged.apply(
        lambda row: resolve_geo(row["programs"], row["vess_flag"]), axis=1
    )

    previous = read_sanctions_current()
    current = compute_diff(previous, tagged.drop(columns=["geo"]), pull_date)

    write_sanctions_current(current)
    write_sanctions_snapshot(tagged.drop(columns=["geo"]), pull_date)
    print(f"ofac: wrote {len(current)} rows to the rolling sanctions table", flush=True)

    newly_listed = tagged[
        (tagged["sanction_id"].isin(current[current["first_seen"] == pull_date]["sanction_id"]))
        & (tagged["energy_related"])
    ]
    if not newly_listed.empty:
        events = sanctions_to_events(newly_listed, pull_date)
        write_events(events, source="ofac")
        print(f"ofac: wrote {len(events)} newly-listed energy-related event rows", flush=True)
    else:
        print("ofac: no newly-listed energy-related rows this pull", flush=True)


if __name__ == "__main__":
    main()
