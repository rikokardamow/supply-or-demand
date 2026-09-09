"""Publish events and OFAC sanctions into the serving layer.

Both mirror `core/schemas.py`, so this is a copy rather than a transformation -- the
columns mean the same thing here as everywhere else in the project.

**Sanctioned vessels are identities, not positions.** The OFAC listing carries a ship's
name, IMO, flag, owner and call sign, and this project has no AIS feed at all (Spec 11 is
unbuilt, and nothing in the lake holds a vessel position). Anything downstream must
present these as "this vessel is listed", never as "this vessel is here".
"""

from __future__ import annotations

from datetime import UTC

import pandas as pd
from core.publish import publish
from core.storage import read_events, read_sanctions_current

# core.schemas' events columns, in order. serving.events mirrors them exactly.
EVENT_COLUMNS = [
    "event_id",
    "ts",
    "headline",
    "source",
    "url",
    "tags",
    "geo",
    "commodity",
    "severity",
]

SANCTION_COLUMNS = [
    "sanction_id",
    "name",
    "entity_type",
    "programs",
    "call_sign",
    "vess_type",
    "vess_flag",
    "vess_owner",
    "imo",
    "remarks",
    "energy_related",
    "status",
    "first_seen",
    "last_seen",
]


def _stringify_list_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Flatten any list-valued column to a comma-joined string.

    `events.tags` is a real list in the lake (core/schemas.py), but serving.events stores
    it as text: a Postgres array would force every reader to handle two shapes for one
    field, and the UI only ever renders it as a label. COPY would otherwise write a
    Python repr like ``['opec', 'sanctions']`` into the column.
    """
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            continue
        out[column] = out[column].map(
            lambda v: ", ".join(str(x) for x in v) if isinstance(v, (list, tuple)) else v
        )
    return out


def main() -> None:
    events = read_events()
    if events.empty:
        raise RuntimeError("no events in the lake -- refusing to report success")

    events = _stringify_list_columns(events, ["tags"])
    published = publish(
        "events",
        events[EVENT_COLUMNS],
        as_of=events["ts"].max().to_pydatetime().replace(tzinfo=UTC),
        source_note=(
            "Tagged events: GDELT and Guardian news, OFAC listings, and self-hosted"
            " social sentiment (Reddit, StockTwits, Polymarket)"
        ),
        key=["event_id"],
        pipeline="events",
    )
    print(f"published {published} events across {events['source'].nunique()} sources")

    sanctions = read_sanctions_current()
    if sanctions.empty:
        raise RuntimeError("no sanctions in the lake -- refusing to report success")

    published = publish(
        "sanctions",
        sanctions[SANCTION_COLUMNS],
        as_of=pd.Timestamp(sanctions["last_seen"].max()).to_pydatetime().replace(tzinfo=UTC),
        source_note="OFAC Specially Designated Nationals list, currently-listed entries",
        key=["sanction_id"],
        pipeline="ofac",
    )
    vessels = int((sanctions["imo"].notna() & (sanctions["imo"] != "")).sum())
    print(f"published {published} sanctions entries, {vessels} carrying an IMO number")


if __name__ == "__main__":
    main()
