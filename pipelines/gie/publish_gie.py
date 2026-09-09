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

from datetime import UTC

from core.publish import publish, seasonal_frame
from core.storage import read_ts_long

SOURCE = "gie"


def main() -> None:
    # source= narrows the DuckDB glob itself; omitting it would scan every partition in
    # the lake before filtering (see apps/dashboard's own unbounded-read fix).
    df = read_ts_long(source=SOURCE)
    if df.empty:
        # An empty read is a defect, not a no-op: this publisher exists because the lake
        # is populated, so zero rows means the pull broke, a partition was renamed, or
        # `data/` was wiped -- all of which this repo has actually seen (see
        # infra/DISASTER_RECOVERY.md). Printing and returning 0 would hand
        # run_scheduled.py an "OK" for a run that published nothing.
        raise RuntimeError(
            f"read 0 rows for source={SOURCE!r} -- the lake is empty or unreadable;"
            " refusing to report success. Run pipelines.gie.pull_daily first."
        )

    # `as_of` is the *data's* own as-of, never wall-clock time (Spec 32 §2). The UI greys
    # a panel once as_of passes the source's staleness threshold (§5, GIE = 2 days), so
    # stamping now() here would make the panel read fresh forever even if GIE's API went
    # down for a week and this republished an unchanged lake every night.
    as_of = df["ts"].max().to_pydatetime().replace(tzinfo=UTC)
    publish(
        "series_long",
        df,
        as_of=as_of,
        source_note="GIE AGSI+ gas storage and ALSI+ LNG, EU aggregate and member countries",
        key=["series_id", "ts"],
        pipeline="gie",
    )
    print(f"published {len(df)} gie rows across {df['series_id'].nunique()} series")

    # The band's width is whatever core.seasonal.default_years() currently spans (2018 to
    # last year, 2020 excluded) -- 7 years today, and one more every 1 January. Read it
    # off the frame rather than hard-coding a number the rows themselves would contradict.
    bands = seasonal_frame(df)
    years = int(bands["years"].max()) if not bands.empty else 0
    publish(
        "seasonal",
        bands,
        as_of=as_of,
        source_note=f"GIE AGSI+/ALSI+ seasonal bands, {years}-year window, 2020 excluded",
        key=["series_id", "doy"],
        pipeline="gie",
    )
    print(f"published {len(bands)} seasonal rows across {bands['series_id'].nunique()} series")


if __name__ == "__main__":
    main()
