"""Spec 31 item 1: working gas storage capacity, the denominator the lake was missing.

pipelines/eia/pull_gas_storage.py ingests weekly working gas in storage, so the lake
can report Bcf but not percent full -- and heading into winter the fullness ratio is
the number that matters. This pull supplies capacity for the same regions.

Region labels deliberately match STORAGE_GEO_MAP's, so every stored volume has a
capacity to divide by. See pipelines/eia/NOTES.md's "Spec 31 routes" section for the
live-confirmed codes, the area-name="NA" quirk this route shares with
natural-gas/stor/wkly, and why SouthCentral_Salt/SouthCentral_Nonsalt have no capacity
counterpart (no salt/non-salt split exists anywhere in this route's 123-series facet
dump) and so are deliberately absent from CAPACITY_GEO_MAP.

Capacity is published in MMcf (million cubic feet); pull_gas_storage.py's weekly
volumes are published in Bcf (billion cubic feet). These units are NOT reconciled
here -- stored exactly as EIA publishes them, per this project's ingest-time
convention. Any conversion belongs in core/ or the page computing the fullness ratio."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

CAPACITY_GEO_MAP: dict[str, str] = {
    "NGM_EPG0_SACW0_R48_MMCF": "L48",
    "NGM_EPG0_SACW0_R83_MMCF": "East",
    "NGM_EPG0_SACW0_R85_MMCF": "Midwest",
    "NGM_EPG0_SACW0_R84_MMCF": "SouthCentral",
    "NGM_EPG0_SACW0_R86_MMCF": "Mountain",
    "NGM_EPG0_SACW0_R91_MMCF": "Pacific",
}

CAPACITY_ROUTE = "natural-gas/stor/cap"
CAPACITY_FREQUENCY = "monthly"

# Capacity (natural-gas/stor/cap) is published in MMcf; the storage volumes it
# denominates (natural-gas/stor/wkly, pull_gas_storage.py) are published in Bcf.
# Deliberately not reconciled at ingest -- see this module's own docstring and this
# project's ingest-time convention. This is the one place the x1000 lives.
MMCF_PER_BCF = 1_000.0


def fullness_pct(storage_bcf: float, capacity_mmcf: float) -> float:
    """Percent full from the two series exactly as EIA publishes them: storage in Bcf
    (natural-gas/stor/wkly), capacity in MMcf (natural-gas/stor/cap). Callers pass both
    raw -- the x1000 lives here so no page has to remember it."""
    return storage_bcf / (capacity_mmcf / MMCF_PER_BCF) * 100.0


def pull_capacity(client: EIAClient) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    return client.get_series(
        route=CAPACITY_ROUTE,
        series=list(CAPACITY_GEO_MAP),
        frequency=CAPACITY_FREQUENCY,
        geo_map=CAPACITY_GEO_MAP,
    )


def main() -> None:
    with failure_scope("eia.pull_gas_capacity"):
        df = pull_capacity(EIAClient())
        # A region that comes back with no rows at all (the whole pull failing, or one
        # of six regions silently missing) must not be reported as success -- record it
        # so failure_scope's raise_if_any() fires on the way out. get_series always
        # builds the series_id column, even on an empty frame, so this is safe when
        # df is wholly empty too.
        for code in sorted(set(CAPACITY_GEO_MAP) - set(df["series_id"])):
            record_failure(code, RuntimeError("no rows returned"))
        if df.empty:
            print("no gas capacity rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} gas capacity rows across {df['geo'].nunique()} regions", flush=True)


if __name__ == "__main__":
    main()
