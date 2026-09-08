"""Spec 31 item 2: hourly demand, demand forecast, net generation and total interchange
by balancing authority.

ERCOT and PJM are the point. pipelines/gridstatus_iso/ cannot reach either -- ERCOT is
behind Incapsula bot protection and PJM needs a Data Miner 2 key -- and they are the two
markets where gas-fired generation most moves the gas book.

electricity/rto/region-data has no `series` facet (400 on facet/series, confirmed live),
so this uses the client's facet-dict path and mints its own series ids via
pipelines/eia/rto.py. Hourly only: no daily or monthly rollup exists, so every run is
bounded to a trailing window."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import (
    HOURLY,
    REGION_TYPES,
    RTO_RESPONDENTS,
    region_series_id,
    respondent_geo,
)

REGION_ROUTE = "electricity/rto/region-data"
DATA_KEY = "value"

# A daily schedule re-pulls three days so the previous two days' revisions land too.
# write_ts_long de-duplicates on revision_date, so re-pulling an unchanged day is a
# no-op rather than a duplicate -- unlike flows, which needs an explicit replace_window
# (see pull_rto_interchange.py).
TRAILING_DAYS = 3


def _hour_bounds(days: int) -> tuple[str, str]:
    """EIA's hourly routes take start/end as YYYY-MM-DDTHH (confirmed live, Task 0)."""
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")


def pull_demand(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    start, end = _hour_bounds(days)
    return client.get_facet_series(
        route=REGION_ROUTE,
        data_key=DATA_KEY,
        facets={"respondent": RTO_RESPONDENTS, "type": REGION_TYPES},
        frequency=HOURLY,
        series_id=region_series_id,
        geo=respondent_geo,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_demand"):
        df = pull_demand(EIAClient(), days=days)
        # A balancing authority that comes back with no rows at all -- the whole pull
        # failing, or one of RTO_RESPONDENTS silently dropping out of the response --
        # must not be reported as success. ERCOT and PJM are the entire justification
        # for this pipeline (gridstatus_iso cannot reach either), so a silently-dropped
        # ERCOT or PJM is the worst-case outcome here specifically -- record it so
        # failure_scope's raise_if_any() fires on the way out. get_facet_series always
        # builds the geo column, even on an empty frame, so this is safe when df is
        # wholly empty too.
        for ba in sorted(set(RTO_RESPONDENTS) - set(df["geo"])):
            record_failure(ba, RuntimeError("no rows returned"))
        if df.empty:
            print("no RTO region rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} RTO region rows across {df['geo'].nunique()} "
            f"balancing authorities ({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor region data.")
    parser.add_argument(
        "--days",
        type=int,
        default=TRAILING_DAYS,
        help=f"trailing window in days (default {TRAILING_DAYS}); pass a larger value "
        "once, to backfill",
    )
    run(parser.parse_args().days)
