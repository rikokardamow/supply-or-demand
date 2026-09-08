"""Spec 31 item 2: balancing-authority constants and the minted series-id scheme for
EIA's Grid Monitor.

Why this exists at all: pipelines/gridstatus_iso/ reaches CAISO and NYISO only. ERCOT is
blocked by Incapsula/Imperva bot protection (confirmed live 403) and PJM requires a Data
Miner 2 key this project does not hold -- and those two are precisely the markets where
gas-fired generation most moves the gas book. EIA's RTO routes cover both.

The three rto/* routes supply NO series id of any kind (they have no `series` facet at
all -- confirmed live, 400 on facet/series). This module mints one per row instead, the
same way get_operational_series mints ELEC.<KEY>.<facets>.<freq>. A minted id is
PERMANENT once written to the lake: changing a scheme later orphans every row already
stored under the old one. See pipelines/eia/CLAUDE.md."""

from __future__ import annotations

from typing import Any

# Balancing authorities, named -- never selected by index.
ERCOT = "ERCO"
PJM = "PJM"
MISO = "MISO"
SPP = "SWPP"
CAISO = "CISO"
NYISO = "NYIS"
ISNE = "ISNE"
LOWER_48 = "US48"

# Deliberately 8 of EIA's 65 Lower-48 balancing authorities, not all of them. Hourly data
# has no daily or monthly rollup on these routes, so 65 BAs x 3 datasets is roughly 8M
# rows a year -- load-research granularity the spec explicitly rejects ("Do not ingest
# sub-regional demand ... it is granular load research, not gas-demand signal"). These
# are the large gas-burning markets plus a national aggregate. Widening this list is a
# constant edit; record the change in CLAUDE.md so coverage stays legible.
RTO_RESPONDENTS: list[str] = [ERCOT, PJM, MISO, SPP, CAISO, NYISO, ISNE, LOWER_48]

# region-data `type` codes -- REPLACE WITH TASK 0's DUMP.
DEMAND = "D"
DEMAND_FORECAST = "DF"
NET_GENERATION = "NG"
TOTAL_INTERCHANGE = "TI"
REGION_TYPES: list[str] = [DEMAND, DEMAND_FORECAST, NET_GENERATION, TOTAL_INTERCHANGE]

# fuel-type-data `fueltype` codes -- REPLACE WITH TASK 0's DUMP.
NATURAL_GAS = "NG"
COAL = "COL"
NUCLEAR = "NUC"
WIND = "WND"
SOLAR = "SUN"
HYDRO = "WAT"
OTHER = "OTH"
FUEL_TYPES: list[str] = [NATURAL_GAS, COAL, NUCLEAR, WIND, SOLAR, HYDRO, OTHER]

HOURLY = "hourly"
_FREQ_SUFFIX = "H"

INTERCHANGE_MODE = "grid_interchange"


def region_series_id(row: dict[str, Any]) -> str:
    """RTO.REGION.<respondent>.<type>.H -- e.g. RTO.REGION.ERCO.D.H."""
    return f"RTO.REGION.{row['respondent']}.{row['type']}.{_FREQ_SUFFIX}"


def fuel_series_id(row: dict[str, Any]) -> str:
    """RTO.FUEL.<respondent>.<fueltype>.H -- e.g. RTO.FUEL.PJM.NG.H.

    The REGION/FUEL segment is what keeps these apart from region_series_id's output:
    both routes carry a `respondent`, and `type=NG` (net generation) collides with
    `fueltype=NG` (natural gas) on the raw facet values alone. Without the segment a
    fuel-mix value would overwrite a net-generation value in the lake, silently."""
    return f"RTO.FUEL.{row['respondent']}.{row['fueltype']}.{_FREQ_SUFFIX}"


def respondent_geo(row: dict[str, Any]) -> str:
    """The balancing authority is the geography for these routes -- there is no
    `area-name` field to normalise, so `_normalise_geo` is never involved."""
    return str(row["respondent"])
