"""Pull the full WPSR weekly picture: stocks, refinery utilisation & gross inputs,
product supplied, and weekly crude imports. See pipelines/eia/CLAUDE.md for series
codes and how they were discovered."""

from __future__ import annotations

from datetime import UTC

import pandas as pd
from core.publish import publish, seasonal_frame
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
    # `as_of` is the data's own as-of -- the latest week ending -- never wall-clock time
    # (Spec 32 §2). The UI greys a panel once as_of passes the source's staleness
    # threshold (§5, WPSR = 8 days); stamping now() would make it read fresh forever
    # even if EIA stopped publishing and this republished an unchanged frame each week.
    as_of = df["ts"].max().to_pydatetime().replace(tzinfo=UTC)
    publish(
        "series_long",
        df,
        as_of=as_of,
        source_note="EIA WPSR, weekly petroleum stocks/supply routes",
        key=["series_id", "ts"],
        pipeline="wpsr",
    )

    # Spec 32 §5's cadence table has wpsr publishing seasonal bands alongside gie.
    # Weekly stocks are the archetypal seasonal-band exhibit, and the band comes from
    # core.seasonal, so 2020 stays excluded (golden rule 4).
    #
    # This builds bands from the freshly-pulled frame rather than the lake, which is only
    # safe because this pull is a full-history re-pull (1982-present) every run. If it is
    # ever narrowed to a trailing window, switch to reading the lake the way
    # pipelines/gie/publish_gie.py does -- otherwise the band silently collapses to a
    # window too short to compute and serving.seasonal keeps last run's rows.
    bands = seasonal_frame(df)
    years = int(bands["years"].max()) if not bands.empty else 0
    published = publish(
        "seasonal",
        bands,
        as_of=as_of,
        # The band spans core.seasonal.default_years() -- 2018 to last year, 2020
        # excluded, so 7 years today and one more every 1 January. Read it off the frame
        # rather than hard-coding a figure the rows' own `years` column would contradict.
        source_note=f"EIA WPSR seasonal bands, {years}-year window, 2020 excluded",
        key=["series_id", "doy"],
        pipeline="wpsr",
    )
    print(f"published {published} seasonal rows across {bands['series_id'].nunique()} series")


if __name__ == "__main__":
    main()
