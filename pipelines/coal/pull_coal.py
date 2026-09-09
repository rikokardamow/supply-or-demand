"""Spec 31 item 4: power-sector coal -- receipts, consumption, stocks, price, heat content.

Coal matters to this book through exactly one channel: coal-to-gas switching in US power
generation, which sets a floor and ceiling on gas demand. coal/consumption-and-quality
carries everything a switching calculation needs -- quantity, price ($/short ton) and heat
content -- in ONE route, which is why the spec chose it over the alternatives.

Deliberately excluded, and these are findings rather than omissions: Coal Markets basin
spot prices (Powder River, Illinois, Appalachia) are S&P Global proprietary per EIA's own
notice, with no bulk history anywhere -- a chart built on them would be empty for months.
API2 and API4, the seaborne thermal benchmarks that actually matter for European gas
substitution, are NEVER published by EIA at all; no amount of EIA work closes that gap.
There is no weekly coal data on the API at any route.

This route has NO `series` facet (400 on facet/series, confirmed live) -- rows are selected
by location+sector and the series id is minted here. A minted id is PERMANENT once written.
source="coal", not "eia": this is the first member of pipelines/coal/, and giving it its
own source keeps read_ts_long(source="coal") meaningful. See pipelines/coal/NOTES.md."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

COAL_SOURCE = "coal"

COAL_ROUTE = "coal/consumption-and-quality"
# `quarterly` and `annual` are the only declared frequencies -- confirmed live. There is
# no monthly or weekly coal data on this API at all.
COAL_FREQUENCY = "quarterly"
_FREQ_SUFFIX = "Q"

# Confirmed live (pipelines/eia/NOTES.md, "coal power-sector code"): "98" is "Electric
# Power", the power-sector aggregate this project needs -- the same aggregate code EIA
# uses for electricity/electric-power-operational-data's sectorid=98. "1" is "Electric
# Utility", a narrower, different sector -- do not use it here.
POWER_SECTOR = "98"

# Confirmed live: US is a real, non-null location value on this route -- the minimum
# useful cut.
LOCATIONS: list[str] = ["US"]

# Named, never selected by index.
RECEIPTS = "receipts"
CONSUMPTION = "consumption"
STOCKS = "stocks"
PRICE = "price"
HEAT_CONTENT = "heat-content"

# Sulfur and ash content are available on this route but deliberately not ingested: they
# describe coal quality for emissions purposes, not the switching economics this item
# exists for. Add them only with a reason.
DATA_KEYS: list[str] = [RECEIPTS, CONSUMPTION, STOCKS, PRICE, HEAT_CONTENT]


def coal_series_id(data_key: str, row: dict[str, object]) -> str:
    """COAL.<DATA_KEY>.<location>-<sector>.Q -- e.g. COAL.PRICE.US-1.Q.

    Deterministic from the row's own facets, following get_operational_series's
    ELEC.<KEY>.<facets>.<freq> precedent. Permanent once written to the lake: changing
    this scheme later orphans every row already stored under the old one."""
    key_id = data_key.upper().replace("-", "_")
    return f"COAL.{key_id}.{row['location']}-{row['sector']}.{_FREQ_SUFFIX}"


def _series_id_for(key: str) -> Callable[[dict[str, Any]], str]:
    """Binds `key` at call time, one closure per DATA_KEYS entry. Without this, a bare
    `lambda row: coal_series_id(key, row)` built directly inside the comprehension below
    would close over the loop variable itself and every lambda would see only its
    *final* value once the loop finished -- a classic late-binding bug that raises
    nothing and silently collapses all five data keys onto one series-id name.
    `test_every_requested_data_key_produced_rows` is what would catch it."""
    return lambda row: coal_series_id(key, row)


def pull_coal(client: EIAClient) -> pd.DataFrame:
    """One frame across every data key. get_facet_series takes a single data_key, so this
    loops -- the same shape get_operational_series uses for its own data_keys list.

    Each key carries its OWN unit ($/short ton for price, MMBtu for heat content, short
    tons for the quantities), stored exactly as published. Never reconcile them here."""
    frames = [
        client.get_facet_series(
            route=COAL_ROUTE,
            data_key=key,
            facets={"location": LOCATIONS, "sector": [POWER_SECTOR]},
            frequency=COAL_FREQUENCY,
            series_id=_series_id_for(key),
            geo=lambda row: str(row["location"]),
            source=COAL_SOURCE,
        )
        for key in DATA_KEYS
    ]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    with failure_scope("coal.pull_coal"):
        df = pull_coal(EIAClient())
        if df.empty:
            print("no coal rows pulled", flush=True)
            return
        write_ts_long(df, source=COAL_SOURCE)
        print(
            f"wrote {len(df)} coal rows across {df['series_id'].nunique()} series",
            flush=True,
        )


if __name__ == "__main__":
    main()
