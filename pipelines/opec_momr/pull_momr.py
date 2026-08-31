"""Downloads and parses the latest OPEC MOMR Excel appendix into ts_long.
revision_date is stamped as the MOMR's own publication month (see parser.py), so
running this monthly naturally accumulates one vintage per month rather than
overwriting -- re-running for a month already downloaded is a no-op download
(cached) plus an idempotent write (same revision_date, same values)."""

from __future__ import annotations

import pandas as pd
from core.storage import write_ts_long

from pipelines.opec_momr.downloader import latest_appendix
from pipelines.opec_momr.parser import parse_appendix


def main() -> None:
    path = latest_appendix()
    # The cached filename encodes the actual MOMR month (may be the prior month
    # if this month's issue isn't published yet) -- parse it back out rather than
    # assuming date.today()'s month, so revision_date matches the real vintage.
    month_name, year_str = path.stem.removeprefix("momr-appendix-").rsplit("-", 1)
    revision_date = pd.Timestamp(f"{month_name} 1, {year_str}")

    df = parse_appendix(path, revision_date)
    write_ts_long(df, source="opec_momr")
    print(f"wrote {len(df)} rows across {df['series_id'].nunique()} series ({path.name})")


if __name__ == "__main__":
    main()
