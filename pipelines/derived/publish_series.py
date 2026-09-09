"""Publish every scalar series in the lake into `serving.series_long`.

The per-pipeline publishers (`pipelines/gie/publish_gie.py`, `pull_wpsr.py`,
`pull_yfinance.py`) each push their own source as part of that pipeline's run, which keeps
the freshest sources current between full runs. This one is the sweep: it walks every
source partition in the lake so the web UI can chart *anything* the lake holds, not only
the handful of sources whose pipelines happen to publish.

Run it after a full `run_scheduled` pass, or on its own. It is idempotent -- the upsert
refreshes rows rather than duplicating them.

**One source at a time, deliberately.** `read_ts_long()` with no `source=` scans every
partition in the lake before filtering; narrowing the glob per source is far cheaper and
keeps peak memory to one source's frame rather than 1.6 million rows at once.

`as_of` is each source's own latest timestamp, so a source that has stopped updating
reports itself stale rather than borrowing another's freshness (Spec 32 §2). That means
one `publish_log` row per source, which is also what the UI's per-pipeline as-of badge
reads.
"""

from __future__ import annotations

from datetime import UTC

from core.failures import failure_scope, record_failure
from core.publish import publish
from core.storage import last_ts_by_source, read_ts_long


def lake_sources() -> list[str]:
    """Every source with at least one `ts_long` row, in a stable order."""
    return sorted(set(last_ts_by_source("ts_long", "revision_date")["source"]))


def main() -> None:
    sources = lake_sources()
    if not sources:
        raise RuntimeError("no ts_long sources in the lake -- refusing to report success")

    total = 0
    # One bad source must not cost the other twenty, but a sweep where every source
    # failed has to exit non-zero rather than print a total of nothing.
    with failure_scope("publish series_long"):
        for source in sources:
            try:
                df = read_ts_long(source=source)
                if df.empty:
                    # last_ts_by_source just said this source has rows, so an empty read
                    # is a real inconsistency, not an empty source.
                    raise ValueError(f"{source}: 0 rows despite appearing in the lake index")

                written = publish(
                    "series_long",
                    df,
                    as_of=df["ts"].max().to_pydatetime().replace(tzinfo=UTC),
                    source_note=f"{source}: {df['series_id'].nunique()} series from the lake",
                    key=["series_id", "ts"],
                    pipeline=source,
                )
                total += written
                print(f"{source}: {written} rows, {df['series_id'].nunique()} series")
            except Exception as exc:
                record_failure(source, exc)

    print(f"published {total} rows across {len(sources)} sources")


if __name__ == "__main__":
    main()
