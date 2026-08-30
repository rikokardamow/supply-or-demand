"""Daily incremental entrypoint for orchestration (Spec 13): re-pulls only the trailing
15 gas-days (both Physical Flow and Nomination, every corridor point) on each run, not the
full 2-year history that pull_flows.py does.

ENTSOG data is revised for ~15 gas-days after publication (per specs/03_entsog-eu-gas-flows.md),
and the `flows` schema has no revision_date column for write_ts_long-style revision-aware
de-dup — a revised value for an already-stored day differs from the old row, so plain
full-row de-dup would keep both, silently double-counting downstream. write_flows's
replace_window drops the stale rows for the exact window just re-pulled before writing the
fresh ones, so late revisions replace outright rather than accumulate."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from core.storage import write_flows

from pipelines.entsog.client import ENTSOGClient
from pipelines.entsog.corridors import validate_corridors
from pipelines.entsog.directory import load_directory
from pipelines.entsog.pull_flows import pull_all_points

REVISION_WINDOW_DAYS = 15


def main() -> None:
    directory = load_directory()
    validate_corridors(directory)

    client = ENTSOGClient()
    end = date.today()
    start = end - timedelta(days=REVISION_WINDOW_DAYS - 1)
    replace_window = (pd.Timestamp(start), pd.Timestamp(end))

    physical = pull_all_points(client.get_physical_flow, start, end, "pipeline")
    write_flows(physical, source="entsog", replace_window=replace_window)
    print(
        f"wrote {len(physical)} physical-flow rows (trailing {REVISION_WINDOW_DAYS} days)",
        flush=True,
    )

    nominations = pull_all_points(client.get_nomination, start, end, "nomination")
    write_flows(nominations, source="entsog", replace_window=replace_window)
    print(
        f"wrote {len(nominations)} nomination rows (trailing {REVISION_WINDOW_DAYS} days)",
        flush=True,
    )


if __name__ == "__main__":
    main()
