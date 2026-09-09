"""Pull the full WPSR weekly picture: stocks, refinery utilisation & gross inputs,
product supplied, and weekly crude imports. See pipelines/eia/NOTES.md for series
codes and how they were discovered."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.publish import publish
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

STOCKS = ["WCESTUS1", "W_EPC0_SAX_YCUOK_MBBL", "WCSSTUS1", "WGTSTUS1", "WDISTUS1", "WTESTUS1"]
UTILISATION = ["WPULEUS3", "W_NA_YUP_R10_PER", "W_NA_YUP_R20_PER", "W_NA_YUP_R30_PER",
               "W_NA_YUP_R40_PER", "W_NA_YUP_R50_PER"]
GROSS_INPUTS = ["WGIRIUS2", "WGIRIP12", "WGIRIP22", "WGIRIP32", "WGIRIP42", "WGIRIP52"]
PRODUCT_SUPPLIED = ["WRPUPUS2", "WGFUPUS2", "WDIUPUS2", "WKJUPUS2"]
WEEKLY_IMPORTS = ["WCEIMUS2"]
NATIONAL_BALANCE = ["WCRRIUS2", "WCRFPUS2", "WCREXUS2", "WTTEXUS2"]


def main() -> None:
    client = EIAClient()

    groups = [
        ("petroleum/stoc/wstk", STOCKS),
        ("petroleum/pnp/wiup", UTILISATION),
        ("petroleum/pnp/wiup", GROSS_INPUTS),
        ("petroleum/cons/wpsup", PRODUCT_SUPPLIED),
        ("petroleum/move/wkly", WEEKLY_IMPORTS),
        ("petroleum/sum/sndw", NATIONAL_BALANCE),
    ]

    frames = [
        client.get_series(route=route, series=series, frequency="weekly")
        for route, series in groups
    ]
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="eia")
    print(f"wrote {len(df)} rows across {len(groups)} route groups")

    # Spec 32 Session 2: first real serving-layer publish. Runs after the lake write
    # above already succeeded and committed, so a publish failure here loses no data --
    # but per core/failures.py's own convention, a failure must still surface as a
    # non-zero exit (never silently swallowed), so infra/run_scheduled.py and Task
    # Scheduler's "Last Run Result" reflect it truthfully.
    publish(
        "series_long",
        df,
        as_of=datetime.now(UTC),
        source_note="EIA WPSR, weekly petroleum stocks/supply routes",
        key=["series_id", "ts"],
        pipeline="wpsr",
    )


if __name__ == "__main__":
    main()
