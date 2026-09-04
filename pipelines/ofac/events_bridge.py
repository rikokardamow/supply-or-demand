"""Bridges newly-listed, energy-related OFAC SDN rows into the existing `events`
lake (Spec 09) -- the actual "connection to other components" this feature centres
on. No new schema, no new overlay component: a newly-sanctioned energy-related
vessel/entity flows through exactly the same `core.storage.write_events` path
GDELT/Guardian/NewsAPI already use, so it automatically surfaces on page 09's map/
feed/table and as a severity-coloured vertical line on pages 01/02/06 via the
already-existing `apps/dashboard/components/event_overlay.py` -- confirmed reusable
as-is, no changes needed there."""

from __future__ import annotations

import hashlib

import pandas as pd

# Confirmed live: https://sanctionssearch.ofac.treas.gov/Details.aspx?id=4238
# returns a real per-entity detail page whose own lblVesselName field literally
# reads "MAR AZUL", matching that ent_num's real vessel name -- a genuine
# per-entity deep link, not a guess.
DETAILS_URL_TEMPLATE = "https://sanctionssearch.ofac.treas.gov/Details.aspx?id={sanction_id}"

# Matches this dashboard's existing small, closed commodity vocabulary
# (crude/gas/power) rather than inventing a new value.
_GAS_KEYWORDS = ["gas", "lng"]


def _event_id(sanction_id: str) -> str:
    """Mirrors pipelines/news/events.py::_event_id's own hash-based stable-key
    pattern -- a stable, deterministic id so re-running the pull never creates a
    duplicate event row for the same sanction."""
    return hashlib.sha256(f"ofac:{sanction_id}".encode()).hexdigest()


def _commodity_for(name: str, remarks: str | None) -> str:
    text = f"{name} {remarks or ''}".lower()
    if any(kw in text for kw in _GAS_KEYWORDS):
        return "gas"
    return "crude"


def _severity_for(entity_type: str) -> int:
    # A vessel is a real physical/shipping sanction -- the same tier this dashboard
    # already reserves for force-majeure-class events (see pipelines/news/tagging.py).
    return 3 if entity_type == "vessel" else 2


def sanctions_to_events(newly_listed: pd.DataFrame, pull_date: pd.Timestamp) -> pd.DataFrame:
    """`newly_listed` is the energy-related subset of this pull's tagged snapshot
    whose sanction_id is genuinely new this pull (first_seen == pull_date) -- the
    caller (pull_ofac.py::main) is responsible for that filtering; this function
    just maps rows to the events schema."""
    return pd.DataFrame(
        {
            "event_id": newly_listed["sanction_id"].map(_event_id),
            "ts": pull_date,
            "headline": newly_listed.apply(
                lambda row: f"OFAC SDN listing: {row['name']} ({', '.join(row['programs'])})",
                axis=1,
            ),
            "source": "ofac",
            "url": newly_listed["sanction_id"].map(
                lambda sid: DETAILS_URL_TEMPLATE.format(sanction_id=sid)
            ),
            "tags": newly_listed["programs"].map(
                lambda programs: ["ofac_sanction", *[p.lower() for p in programs]]
            ),
            "geo": newly_listed["geo"],
            "commodity": newly_listed.apply(
                lambda row: _commodity_for(row["name"], row["remarks"]), axis=1
            ),
            "severity": newly_listed["entity_type"].map(_severity_for),
            "language": "unknown",
        }
    )
