"""Spec 31 item 2: hourly generation by fuel type, per balancing authority.

Gas-fired generation in ERCOT and PJM is the gas-demand signal this item exists for --
coal-to-gas switching sets a floor and ceiling on power-sector gas burn, and these are the
two markets pipelines/gridstatus_iso/ cannot reach.

electricity/rto/fuel-type-data has no `series` facet (400 on facet/series, confirmed
live); facets are respondent+fueltype. Hourly only, so every run is bounded."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.rto import (
    FUEL_TYPES,
    HOURLY,
    RTO_RESPONDENTS,
    fuel_series_id,
    respondent_geo,
)

FUEL_ROUTE = "electricity/rto/fuel-type-data"
DATA_KEY = "value"
TRAILING_DAYS = 3


def _hour_bounds(days: int) -> tuple[str, str]:
    """EIA's hourly routes take start/end as YYYY-MM-DDTHH (confirmed live, Task 0)."""
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H"), now.strftime("%Y-%m-%dT%H")


def pull_fuel_mix(client: EIAClient, days: int = TRAILING_DAYS) -> pd.DataFrame:
    start, end = _hour_bounds(days)
    return client.get_facet_series(
        route=FUEL_ROUTE,
        data_key=DATA_KEY,
        facets={"respondent": RTO_RESPONDENTS, "fueltype": FUEL_TYPES},
        frequency=HOURLY,
        series_id=fuel_series_id,
        geo=respondent_geo,
        start=start,
        end=end,
    )


def run(days: int) -> None:
    with failure_scope("eia.pull_rto_fuel_mix"):
        df = pull_fuel_mix(EIAClient(), days=days)
        # A balancing authority that comes back with no rows at all -- the whole pull
        # failing, or one of RTO_RESPONDENTS silently dropping out of the response --
        # must not be reported as success. Gas-fired generation in ERCOT and PJM is the
        # actual gas-demand signal this item exists to capture, so a silently-dropped
        # ERCOT or PJM is the worst-case outcome here specifically -- record it so
        # failure_scope's raise_if_any() fires on the way out. get_facet_series always
        # builds the geo column, even on an empty frame, so this is safe when df is
        # wholly empty too.
        for ba in sorted(set(RTO_RESPONDENTS) - set(df["geo"])):
            record_failure(ba, RuntimeError("no rows returned"))
        if df.empty:
            print("no RTO fuel-mix rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} RTO fuel-mix rows across {df['geo'].nunique()} "
            f"balancing authorities ({days}d window)",
            flush=True,
        )


def main() -> None:
    run(TRAILING_DAYS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull EIA Grid Monitor fuel-type data.")
    parser.add_argument("--days", type=int, default=TRAILING_DAYS)
    run(parser.parse_args().days)
