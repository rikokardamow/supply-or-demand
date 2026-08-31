"""Downloads Baker Hughes' current weekly North America rig count and writes
it to ts_long. This *is* the Friday entrypoint (per the spec) -- the sheet
itself already carries the full weekly history (confirmed live, ~2.7 years),
so there's no separate one-off-backfill-vs-narrow-window split the way
ENTSO-E/EirGrid needed; running this weekly naturally keeps the lake current,
and write_ts_long's revision-based de-dup makes re-running it idempotent."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.baker_hughes.client import download_current_report
from pipelines.baker_hughes.parser import parse_weekly_rig_counts


def main() -> None:
    path, report_date = download_current_report()
    revision_date = pd.Timestamp(datetime.now(UTC))

    df = parse_weekly_rig_counts(str(path), revision_date)
    write_ts_long(df, source="baker_hughes")
    print(
        f"wrote {len(df)} rows across {df['series_id'].nunique()} series "
        f"(report date {report_date}, {path.name})"
    )


if __name__ == "__main__":
    main()
