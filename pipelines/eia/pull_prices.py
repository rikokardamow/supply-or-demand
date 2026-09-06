"""Spec 30: the price families the lake was missing. Volumes were everywhere and
prices almost nowhere -- one gas price (fred.dhhngsp), no retail pump prices at all,
and no grade-differentiated crude price beneath Spec 19's quality-mismatch work or
Spec 20's crack VECM.

Series codes were discovered live via EIAClient.list_series, never guessed from a
dnav URL -- see pipelines/eia/CLAUDE.md for the real dumps and counts. This module
covers the petroleum, gas and generator-fuel price routes Task 0 confirmed: refiner
acquisition cost, retail pump prices, gravity-banded landed cost of imported crude (a
route the spec's own six candidates didn't name -- found by walking
GET /v2/petroleum/pri), citygate/sectoral delivered gas prices, and the average cost of
gas delivered to electric generators (a route with no `series` facet at all -- see
EIAClient.get_operational_series).

Units are written exactly as EIA publishes them and are never converted here;
conversion belongs in core/, not in a pipeline."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Refiner acquisition cost of crude oil -- composite, domestic and imported, US and
# PADD level. The price refiners actually paid, as opposed to what the benchmark
# printed. Confirmed live: 631 rows on R0000____3, no nulls.
RAC: list[str] = [
    "R0000____3",  # US composite
    "R1200____3",  # US domestic
    "R1300____3",  # US imported
    "R0010____3",  # PADD1 composite
    "R0020____3",  # PADD2 composite
    "R0030____3",  # PADD3 composite
    "R0040____3",  # PADD4 composite
    "R0050____3",  # PADD5 composite
]

# Retail gasoline (all grades, all formulations) and No. 2 diesel (unrestricted
# sulfur grade), US and PADD level. Confirmed live: 1,744 rows on
# EMM_EPM0_PTE_NUS_DPG, no nulls.
RETAIL: list[str] = [
    "EMM_EPM0_PTE_NUS_DPG",  # US gasoline
    "EMM_EPM0_PTE_R10_DPG",  # PADD1 gasoline
    "EMM_EPM0_PTE_R20_DPG",  # PADD2 gasoline
    "EMM_EPM0_PTE_R30_DPG",  # PADD3 gasoline
    "EMM_EPM0_PTE_R40_DPG",  # PADD4 gasoline
    "EMM_EPM0_PTE_R50_DPG",  # PADD5 gasoline
    "EMD_EPD2D_PTE_NUS_DPG",  # US diesel
    "EMD_EPD2D_PTE_R10_DPG",  # PADD1 diesel
    "EMD_EPD2D_PTE_R20_DPG",  # PADD2 diesel
    "EMD_EPD2D_PTE_R30_DPG",  # PADD3 diesel
    "EMD_EPD2D_PTE_R40_DPG",  # PADD4 diesel
    "EMD_EPD2D_PTE_R50_DPG",  # PADD5 diesel
]

# Landed cost of imported crude by API gravity band -- petroleum/pri/land3. Not one
# of Spec 30's six named candidate routes; found by walking GET /v2/petroleum/pri
# (pipelines/eia/CLAUDE.md). Confirmed live: 522 rows on I000000208, 1983-01 to
# 2026-06, no nulls.
LAND3_ROUTE = "petroleum/pri/land3"

LANDED_COST: list[str] = [
    "I000000208",  # API gravity 20.0 degrees or less
    "I000000258",  # API gravity 20.1 to 25.0 degrees
    "I000000308",  # API gravity 25.1 to 30.0 degrees
    "I000000358",  # API gravity 30.1 to 35.0 degrees
    "I000000408",  # API gravity 35.1 to 40.0 degrees
    "I000000458",  # API gravity 40.1 to 45.0 degrees
    "I000000998",  # API gravity 45.1 degrees or more
]

# petroleum/pri/land3 returns area-name as the literal string "NA" for every row
# (confirmed live, same quirk as natural-gas/stor/wkly) -- geo must come from this
# explicit map, not EIAClient._normalise_geo(area-name). Labels are the gravity band
# each code covers, per the real series names confirmed live via list_series().
LANDED_COST_GEO_MAP: dict[str, str] = {
    "I000000208": "US-API-LE20",
    "I000000258": "US-API-20-25",
    "I000000308": "US-API-25-30",
    "I000000358": "US-API-30-35",
    "I000000408": "US-API-35-40",
    "I000000458": "US-API-40-45",
    "I000000998": "US-API-GT45",
}

# Citygate and sectoral delivered gas prices, from natural-gas/pri/sum. The lake holds
# one gas price (fred.dhhngsp, Henry Hub spot) and nothing to locate it against, so
# basis is uncomputable today. natural-gas/pri/rescom (state-level only, no national
# row) and natural-gas/pri/fut (duplicates fred.dhhngsp and Spec 18's futures) are both
# out of scope -- see pipelines/eia/CLAUDE.md's "Spec 30 price routes" section.
GAS: list[str] = ["N3050US3", "N3010US3", "N3020US3", "N3035US3"]

# EPM Table 4.13's average cost of natural gas delivered to electric generators
# ($/MMBtu) and Table 2.4's gas consumed for generation -- the direct gas-to-power
# bridge. electricity/electric-power-operational-data has no `series` facet at all
# (confirmed live -- pipelines/eia/CLAUDE.md); these are the two `data[0]` keys
# EIAClient.get_operational_series requests, not series ids -- the series ids it mints
# from them are documented there and in that method's own docstring.
GENERATOR_FUEL_ROUTE = "electricity/electric-power-operational-data"
GENERATOR_FUEL_FUELTYPEID = "NG"
GENERATOR_FUEL_SECTORID = "98"  # "(98) Electric Power" -- the sector aggregate, not a
# narrower IPP/CHP/utility sub-sector also on offer under the same facet.

# State-level, not national-only: Spec 30's own chart ("State delivered gas cost to
# generators vs Henry Hub, with the spread annotated") needs the dispersion across
# states, which a single national average would wash out. "US" is kept too -- it is the
# national benchmark line the state series get compared against.
#
# These 10 codes are the ones Task 0 confirmed live carry a real (non-null) latest
# value; `location` also mixes in 51 real states/DC/PR and 11 census-division
# aggregates under the same facet with no way to separate them structurally, so the
# rest cannot be added by pattern. FL, NC, GA, AZ, CO, OK, WV and WA were checked and
# excluded because they returned `cost-per-btu: null` for 2026-06 rather than a real
# value -- see pipelines/eia/CLAUDE.md's "Spec 30 price routes" section (checked
# 2026-09-06). Nulls are always skipped by EIAClient.get_operational_series, never
# written as a fabricated zero.
GENERATOR_FUEL_LOCATIONS: list[str] = [
    "US", "TX", "CA", "PA", "LA", "OH", "NY", "IL", "NJ", "MI"
]

GENERATOR_FUEL: list[str] = ["cost-per-btu", "consumption-for-eg"]

MONTHLY_GROUPS: list[tuple[str, list[str], str]] = [
    ("petroleum/pri/rac2", RAC, "monthly"),
    (LAND3_ROUTE, LANDED_COST, "monthly"),
    ("natural-gas/pri/sum", GAS, "monthly"),
    (GENERATOR_FUEL_ROUTE, GENERATOR_FUEL, "monthly"),
]

WEEKLY_GROUPS: list[tuple[str, list[str], str]] = [
    ("petroleum/pri/gnd", RETAIL, "weekly"),
]

# Only land3 needs an explicit geo_map (see above); every other route here gets a
# clean geo from area-name via EIAClient's default behaviour.
_GEO_MAPS: dict[str, dict[str, str]] = {
    LAND3_ROUTE: LANDED_COST_GEO_MAP,
}


def pull_group(
    client: EIAClient,
    route: str,
    series: list[str],
    frequency: str,
    geo_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One route's worth of rows. Kept separate from pull_all so a single route can be
    exercised directly by a cassette test.

    GENERATOR_FUEL_ROUTE has no `series` facet at all (see GENERATOR_FUEL above) and is
    routed to EIAClient.get_operational_series instead of get_series -- every other
    route here is series-facet-based and unaffected."""
    if route == GENERATOR_FUEL_ROUTE:
        return client.get_operational_series(
            route=route,
            data_keys=series,
            fueltypeid=GENERATOR_FUEL_FUELTYPEID,
            sectorid=GENERATOR_FUEL_SECTORID,
            locations=GENERATOR_FUEL_LOCATIONS,
            frequency=frequency,
        )
    return client.get_series(route=route, series=series, frequency=frequency, geo_map=geo_map)


def pull_all(groups: list[tuple[str, list[str], str]]) -> list[pd.DataFrame]:
    """Per-route resilience, matching pipelines/adanos/pull_adanos.py: one route
    failing is recorded and skipped, never raised here, so the rest of the pull still
    runs. failure_scope in main() turns any recorded failure into a non-zero exit."""
    client = EIAClient()
    frames: list[pd.DataFrame] = []
    for route, series, frequency in groups:
        try:
            df = pull_group(client, route, series, frequency, geo_map=_GEO_MAPS.get(route))
        except Exception as exc:  # one route must never abort the rest
            record_failure(f"eia prices {route}", exc)
            continue
        print(f"eia prices {route}: {len(df)} rows", flush=True)
        frames.append(df)
    return frames


def main() -> None:
    with failure_scope("eia.pull_prices"):
        frames = pull_all(MONTHLY_GROUPS)
        if not frames:
            print("no EIA price rows pulled", flush=True)
            return
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} EIA price rows", flush=True)


def main_weekly() -> None:
    with failure_scope("eia.pull_prices_weekly"):
        frames = pull_all(WEEKLY_GROUPS)
        if not frames:
            print("no weekly EIA price rows pulled", flush=True)
            return
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} weekly EIA price rows", flush=True)


if __name__ == "__main__":
    main()
