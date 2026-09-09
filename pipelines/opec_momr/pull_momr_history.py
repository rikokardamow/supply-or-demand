"""Backfill every OPEC MOMR appendix OPEC still serves, one vintage per month.

`pull_momr.py` fetches the newest issue. That is right for the monthly cadence but it
means the lake only ever holds vintages from the day this project started running --
which is why the site showed eight quarters of a forward forecast and nothing behind it.
Each appendix carries its own forward window stamped with the MOMR's own publication
month as `revision_date`, so downloading the back issues builds a real series of vintages
and lets a reader see how OPEC's view of a quarter moved between issues.

**Availability is patchy, not a rolling window -- confirmed live 2026-09-09.** OPEC's
static appendix URLs returned HTTP 200 for March to September 2025 and for January 2026
onward, but **403 for October, November and December 2025** -- months sitting *between*
two available stretches, so this is per-file, not retention. February 2025 and earlier
also 403. A backfill therefore has to probe every month and report what is missing
rather than assume a contiguous range; assuming one would silently skip the tail.

The PDF is a separate matter: `momr.opec.org/pdf-download/` sits behind a Cloudflare JS
challenge and returns a 403 "Just a moment..." page to any client without a browser. The
Excel appendix needs no such workaround, carries the same tables in a parseable form, and
is what this pipeline uses. Do not add a headless browser to scrape the PDF when the
spreadsheet is served cleanly.
"""

from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.opec_momr.downloader import download_appendix
from pipelines.opec_momr.parser import parse_appendix

# Nothing before this has been served since at least 2026-09; probing further back only
# adds 403s. Widen it if OPEC republishes an archive.
EARLIEST_MONTH = date(2025, 1, 1)


def months_between(start: date, end: date) -> list[date]:
    """Every month start from `start` to `end` inclusive, oldest first."""
    months: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return months


def main(start: date = EARLIEST_MONTH, end: date | None = None) -> None:
    end = end or date.today()
    wanted = months_between(start, end)

    written = 0
    got: list[date] = []
    missing: list[date] = []

    # One month's absence must not stop the backfill -- most of the range is expected to
    # be missing -- but a run where every month failed has to exit non-zero rather than
    # report a cheerful zero.
    with failure_scope("momr history"):
        for month in wanted:
            try:
                path = download_appendix(month)
            except Exception:
                # A 403 or 404 here is the normal case for an unpublished month, not a
                # failure worth recording: OPEC simply does not serve it.
                missing.append(month)
                continue

            try:
                df = parse_appendix(path, pd.Timestamp(month))
                write_ts_long(df, source="opec_momr")
                written += len(df)
                got.append(month)
                print(f"{month:%b %Y}: {len(df)} rows")
            except Exception as exc:
                # A month that downloaded but would not parse IS a real failure -- the
                # file exists and the parser should handle it.
                record_failure(f"{month:%B %Y}", exc)

    if not got:
        raise RuntimeError(
            f"no MOMR appendix could be downloaded for any month in {start:%b %Y}"
            f" to {end:%b %Y}; OPEC may have changed the URL pattern"
        )

    print(
        f"wrote {written} rows from {len(got)} issues "
        f"({got[0]:%b %Y} to {got[-1]:%b %Y}); {len(missing)} month(s) not served: "
        f"{', '.join(f'{m:%b %Y}' for m in missing) or 'none'}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-year", type=int, default=EARLIEST_MONTH.year, help="first year to probe"
    )
    args = parser.parse_args()
    main(start=date(args.from_year, 1, 1))
