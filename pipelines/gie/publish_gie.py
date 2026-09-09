"""Publish GIE gas/LNG storage into the Supabase serving layer (Spec 32 Session 3).

Reads the **lake**, not a freshly-pulled frame. `pull_daily.py` only re-fetches a
trailing 5-day window (GIE revises recent gas-days), so publishing its own output would
put five days into `serving.series_long` and leave the seasonal band with nothing to be
computed from. The lake already holds the full 2018-present history that both the UI's
history charts and `core.seasonal`'s band need.

Run after `pull_daily.py`, or standalone -- it is idempotent, so re-running only
refreshes `serving.publish_log`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.publish import publish, seasonal_frame
from core.storage import read_ts_long

SOURCE = "gie"


def main() -> None:
    # source= narrows the DuckDB glob itself; omitting it would scan every partition in
    # the lake before filtering (see apps/dashboard's own unbounded-read fix).
    df = read_ts_long(source=SOURCE)
    if df.empty:
        print("gie: nothing in the lake to publish")
        return

    as_of = datetime.now(UTC)
    publish(
        "series_long",
        df,
        as_of=as_of,
        source_note="GIE AGSI+ gas storage and ALSI+ LNG, EU aggregate and member countries",
        key=["series_id", "ts"],
        pipeline="gie",
    )
    print(f"published {len(df)} gie rows across {df['series_id'].nunique()} series")

    bands = seasonal_frame(df)
    publish(
        "seasonal",
        bands,
        as_of=as_of,
        source_note="GIE AGSI+/ALSI+ seasonal bands, 5-year window, 2020 excluded",
        key=["series_id", "doy"],
        pipeline="gie",
    )
    print(f"published {len(bands)} seasonal rows across {bands['series_id'].nunique()} series")


if __name__ == "__main__":
    main()
