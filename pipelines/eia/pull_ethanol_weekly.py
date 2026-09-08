"""Spec 31 item 6: weekly ethanol production, national and all five PADDs.

The best trading-frequency proxy for ethanol blending economics, and weekly -- the same
cadence as the WPSR series already in the lake, so it registers in the existing "wpsr"
scheduler group rather than needing a new rhythm.

Plan 31A's Task 0 corrected the spec here, live: this route carries PADD1 THROUGH PADD5
(6 series in total), not PADD1-4 as an earlier draft said. All six are ingested; omitting
PADD5 would silently lose the West Coast. See pipelines/eia/NOTES.md.

All six series resolve `area-name` cleanly via `EIAClient.get_series`'s existing
`_normalise_geo` -- confirmed live by Spec 31C's Task 0 -- so no `geo_map` is needed here,
unlike natural-gas/stor/cap or petroleum/pri/land3."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Named, never selected by index -- see this module's test.
US = "W_EPOOXE_YOP_NUS_MBBLD"
PADD1 = "W_EPOOXE_YOP_R10_MBBLD"
PADD2 = "W_EPOOXE_YOP_R20_MBBLD"
PADD3 = "W_EPOOXE_YOP_R30_MBBLD"
PADD4 = "W_EPOOXE_YOP_R40_MBBLD"
PADD5 = "W_EPOOXE_YOP_R50_MBBLD"

ETHANOL: list[str] = [US, PADD1, PADD2, PADD3, PADD4, PADD5]

ETHANOL_ROUTE = "petroleum/pnp/wprode"
# `weekly` confirmed live; the route also declares `four-week-average` and nothing else.
# A wrong frequency here returns empty rather than erroring.
ETHANOL_FREQUENCY = "weekly"


def pull_ethanol(client: EIAClient) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    return client.get_series(
        route=ETHANOL_ROUTE, series=ETHANOL, frequency=ETHANOL_FREQUENCY
    )


def main() -> None:
    with failure_scope("eia.pull_ethanol_weekly"):
        df = pull_ethanol(EIAClient())
        if df.empty:
            print("no ethanol rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(
            f"wrote {len(df)} weekly ethanol rows across {df['geo'].nunique()} regions",
            flush=True,
        )


if __name__ == "__main__":
    main()
