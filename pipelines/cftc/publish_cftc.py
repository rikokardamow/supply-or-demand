"""Publish CFTC Commitments of Traders into the Supabase serving layer.

Reads the **lake**, not a freshly-pulled frame -- `pull_weekly.py` only re-fetches a
trailing 8-week window, so publishing its own output would put eight weeks into
`serving.series_long` and leave every history chart with nothing to draw. The lake holds
2006-present for the NYMEX contracts and 2011-present for Brent.

No seasonal band, deliberately. `core.seasonal` builds a day-of-year curve, and COT is a
weekly report stamped on the Tuesday: normalising 52 points a year onto a 365-day grid
would forward-fill each reading across the six days after it and present the result as a
daily band. Positioning is compared against its own percentile history, not against a
seasonal shape, so the band would be an artefact nobody asked for.

Net managed money (`mm_long - mm_short`) is not published either. It is a read-time
transform, the same call `pipelines/gie/transforms.py:net_flow` makes for storage flows:
storing a difference alongside its own two operands invites the three to disagree.

Run after `pull_weekly.py`, or standalone -- it is idempotent, so re-running only refreshes
`serving.publish_log`.
"""

from __future__ import annotations

from datetime import UTC

from core.publish import publish
from core.storage import read_ts_long

SOURCE = "cftc"


def main() -> None:
    # source= narrows the DuckDB glob itself; omitting it would scan every partition in the
    # lake before filtering.
    df = read_ts_long(source=SOURCE)
    if df.empty:
        # An empty read is a defect, not a no-op: this publisher exists because the lake is
        # populated, so zero rows means the pull broke, a partition was renamed, or `data/`
        # was wiped. Printing and returning 0 would hand run_scheduled.py an "OK" for a run
        # that published nothing.
        raise RuntimeError(
            f"read 0 rows for source={SOURCE!r} -- the lake is empty or unreadable;"
            " refusing to report success. Run pipelines.cftc.pull_history first."
        )

    # The *data's* own as-of, never wall-clock time. COT reports a Tuesday and is released
    # the following Friday at 15:30 ET, so a current report is already three days old as
    # data and a stale one looks no different from wall-clock time.
    as_of = df["ts"].max().to_pydatetime().replace(tzinfo=UTC)
    rows = publish(
        "series_long",
        df,
        as_of=as_of,
        source_note=(
            "CFTC Commitments of Traders, disaggregated futures-only: managed money and "
            "producer/merchant long and short, and open interest, for WTI, Brent, RBOB "
            "and heating oil"
        ),
        key=["series_id", "ts"],
        pipeline=SOURCE,
    )
    print(f"published {rows} cftc rows across {df['series_id'].nunique()} series")


if __name__ == "__main__":
    main()
