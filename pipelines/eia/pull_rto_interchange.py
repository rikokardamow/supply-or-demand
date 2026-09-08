"""Spec 31 item 2: hourly interchange between balancing authorities, as `flows` rows.

The spec calls this out specifically: interchange-data maps onto the `flows` schema and
the corridor pattern pipelines/eia/corridors.py already establishes. Unlike the crude PADD
corridors, though, the corridor is not looked up from a series id -- this route carries
`fromba` and `toba` on every row, so each row names its own corridor.

electricity/rto/interchange-data has no `series` facet (400 on facet/series, confirmed
live) and, uniquely among the three rto/* routes, no `type` or `fueltype` facet either --
just fromba+toba."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope
from core.storage import write_flows

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import HOURLY, INTERCHANGE_MODE, RTO_RESPONDENTS

INTERCHANGE_ROUTE = "electricity/rto/interchange-data"
DATA_KEY = "value"
TRAILING_DAYS = 3


def _window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(days=days), now


def _hour_bounds(days: int) -> tuple[str, str]:
    start, end = _window(days)
    return start.strftime("%Y-%m-%dT%H"), end.strftime("%Y-%m-%dT%H")


def pull_interchange(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    """Filtered by `fromba` only. Every corridor OUT of the chosen BAs is returned, and
    each row names its own counterparty in `toba` -- so a corridor to a BA outside
    RTO_RESPONDENTS is still captured, which is wanted: ERCOT's ties to its neighbours
    are part of the ERCOT picture even when the neighbour is not itself ingested."""
    start, end = _hour_bounds(days)
    return client.get_facet_flows(
        route=INTERCHANGE_ROUTE,
        data_key=DATA_KEY,
        facets={"fromba": RTO_RESPONDENTS},
        frequency=HOURLY,
        mode=INTERCHANGE_MODE,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_interchange"):
        df = pull_interchange(EIAClient(), days=days)
        if df.empty:
            print("no RTO interchange rows pulled", flush=True)
            return
        # REQUIRED, not optional. flows has no revision_date column, so write_flows
        # cannot tell a revised value from a new row -- it would keep both, and every
        # downstream sum would double-count, silently. The window must be derived from
        # the pulled frame's own `ts` column, not a second `datetime.now(UTC)` call --
        # the API call happens between `pull_interchange`'s internal `_window(days)` and
        # any later clock read here, so a second reading is always a little later and
        # leaves the oldest pulled hour outside the window, unreplaced. `ts` is already
        # tz-naive (built via pd.to_datetime on EIA's tz-naive period strings), matching
        # what write_flows/_normalise_datetime_tz expect on disk.
        window_start = df["ts"].min().to_pydatetime()
        window_end = df["ts"].max().to_pydatetime()
        write_flows(
            df,
            source="eia",
            replace_window=(window_start, window_end),
        )
        pairs = df[["from_node", "to_node"]].drop_duplicates()
        print(
            f"wrote {len(df)} RTO interchange rows across {len(pairs)} corridors "
            f"({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor interchange data.")
    parser.add_argument("--days", type=int, default=TRAILING_DAYS)
    run(parser.parse_args().days)
