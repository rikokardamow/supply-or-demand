"""Spec 31 item 5: biofuels production capacity and the feedstocks fed into it.

Two routes, one item, because they are only interpretable together. petroleum/pnp/capbio
is monthly national capacity for biodiesel, renewable diesel and fuel ethanol -- the
signal for renewable diesel capacity displacing petroleum diesel demand.
petroleum/pnp/feedbiofuel carries the monthly feedstock inputs (soybean oil, corn oil,
used cooking oil, tallow, canola), which is what QUANTIFIES feedstock competition rather
than merely asserting it.

Note this module's pull_capacity() is BIOFUEL production capacity. pipelines/eia/
pull_gas_capacity.py has a same-named function for natural gas STORAGE capacity; they are
unrelated. Both are national and monthly; neither needs a geo_map (area-name resolves to
"U.S." cleanly on both routes -- confirmed live). See pipelines/eia/NOTES.md."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# capbio -- 3 series, all US national. Named, never selected by index.
BIODIESEL = "M_EPOORDB_8BDPC_NUS_MMGL"
RENEWABLE_DIESEL = "M_EPOOROO_8BDPC_NUS_MMGL"
FUEL_ETHANOL = "M_EPOOXE_8BDPC_NUS_MMGL"

CAPACITY: list[str] = [BIODIESEL, RENEWABLE_DIESEL, FUEL_ETHANOL]

# feedbiofuel -- Task 0's full 26-series dump, sorted by id (pipelines/eia/NOTES.md).
FEEDSTOCKS: list[str] = [
    "M_EPOOBDAFC_YIFBP_NUS_MMLB",
    "M_EPOOBDAFD_YIFBP_NUS_MMLB",
    "M_EPOOBDAFO_YIFBP_NUS_MMLB",
    "M_EPOOBDAFPO_YIFBP_NUS_MMLB",
    "M_EPOOBDAFR_YIFBP_NUS_MMLB",
    "M_EPOOBDAFS_YIFBP_NUS_MMLB",
    "M_EPOOBDAL_YIFBP_NUS_MMLB",
    "M_EPOOBDBG_YIFBP_NUS_MMLB",
    "M_EPOOBDCNOD_YIFBP_NUS_MMLB",
    "M_EPOOBDCNOR_YIFBP_NUS_MMLB",
    "M_EPOOBDCNO_YIFBP_NUS_MMLB",
    "M_EPOOBDCOD_YIFBP_NUS_MMLB",
    "M_EPOOBDCOR_YIFBP_NUS_MMLB",
    "M_EPOOBDCO_YIFBP_NUS_MMLB",
    "M_EPOOBDFSPT_YIFBP_NUS_MMLB",
    "M_EPOOBDFSTL_YIFBP_NUS_MMLB",
    "M_EPOOBDFSWG_YIFBP_NUS_MMLB",
    "M_EPOOBDFSYG_YIFBP_NUS_MMLB",
    "M_EPOOBDOB_YIFBP_NUS_MMLB",
    "M_EPOOBDRFWM_YIFBP_NUS_MMLB",
    "M_EPOOBDRFWO_YIFBP_NUS_MMLB",
    "M_EPOOBDRFWY_YIFBP_NUS_MMLB",
    "M_EPOOBDSOD_YIFBP_NUS_MMLB",
    "M_EPOOBDSOR_YIFBP_NUS_MMLB",
    "M_EPOOBDSO_YIFBP_NUS_MMLB",
    "M_EPOOBDVOO_YIFBP_NUS_MMLB",
]

# Guards against a silently truncated paste of the list above. Task 0 counted this;
# a mismatch means the constant is incomplete, not that the route changed.
EXPECTED_FEEDSTOCK_COUNT = 26

# Task 2 (31C), confirmed live: these 4 of the 26 FEEDSTOCKS report a literal null value
# for every one of their recorded periods (2021-01 to 2026-06) -- dedicated energy crops,
# biogas, municipal solid waste, yard/food waste. EIAClient.get_series's null-skip
# correctly drops them to zero rows, forever, unless EIA someday starts reporting real
# values. Excluded here from the missing-member failure check so a healthy pull isn't
# flagged as partially failed on every single run -- see pipelines/eia/NOTES.md's
# Task 2 (31C) entry and tests/test_eia_biofuels.py.
ALWAYS_NULL_FEEDSTOCKS: set[str] = {
    "M_EPOOBDAFD_YIFBP_NUS_MMLB",
    "M_EPOOBDBG_YIFBP_NUS_MMLB",
    "M_EPOOBDRFWM_YIFBP_NUS_MMLB",
    "M_EPOOBDRFWY_YIFBP_NUS_MMLB",
}

CAPACITY_ROUTE = "petroleum/pnp/capbio"
FEEDSTOCK_ROUTE = "petroleum/pnp/feedbiofuel"
# Both routes declare `monthly` only -- confirmed live. A wrong frequency returns empty.
BIOFUEL_FREQUENCY = "monthly"


def pull_capacity(client: EIAClient) -> pd.DataFrame:
    """Biofuel PRODUCTION capacity -- not natural gas storage capacity."""
    return client.get_series(
        route=CAPACITY_ROUTE, series=CAPACITY, frequency=BIOFUEL_FREQUENCY
    )


def pull_feedstocks(client: EIAClient) -> pd.DataFrame:
    return client.get_series(
        route=FEEDSTOCK_ROUTE, series=FEEDSTOCKS, frequency=BIOFUEL_FREQUENCY
    )


def main() -> None:
    # A single failure_scope, with a try/except around each route: failure_scope alone
    # does NOT isolate one route's exception from the other -- it only collects
    # record_failure calls and raises once at the end, it never catches an exception
    # raised by its own body. Two separate failure_scope context managers (the previous
    # shape here) therefore did not give real per-route resilience, since an exception
    # from pull_capacity would propagate straight out of the first `with` block before
    # pull_feedstocks ever ran. This shape -- one scope, try/except per route -- is what
    # actually matches pipelines/eia/pull_prices.py's pull_all precedent: one route
    # failing is recorded and skipped, never raised here, so the rest of the pull still
    # runs; failure_scope turns any recorded failure into a non-zero exit on the way out.
    with failure_scope("eia.pull_biofuels"):
        client = EIAClient()

        try:
            capacity = pull_capacity(client)
        except Exception as exc:  # one route must never abort the other
            record_failure("eia biofuels capacity", exc)
        else:
            for series_id in sorted(set(CAPACITY) - set(capacity["series_id"])):
                record_failure(series_id, RuntimeError("no rows returned"))
            if capacity.empty:
                print("no biofuel capacity rows pulled", flush=True)
            else:
                write_ts_long(capacity, source="eia")
                print(f"wrote {len(capacity)} biofuel capacity rows", flush=True)

        try:
            feedstocks = pull_feedstocks(client)
        except Exception as exc:  # one route must never abort the other
            record_failure("eia biofuels feedstocks", exc)
        else:
            missing = set(FEEDSTOCKS) - ALWAYS_NULL_FEEDSTOCKS - set(feedstocks["series_id"])
            for series_id in sorted(missing):
                record_failure(series_id, RuntimeError("no rows returned"))
            if feedstocks.empty:
                print("no biofuel feedstock rows pulled", flush=True)
            else:
                write_ts_long(feedstocks, source="eia")
                print(
                    f"wrote {len(feedstocks)} biofuel feedstock rows across "
                    f"{feedstocks['series_id'].nunique()} feedstocks",
                    flush=True,
                )


if __name__ == "__main__":
    main()
