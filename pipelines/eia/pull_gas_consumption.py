"""Spec 31 item 3: natural gas consumption by sector -- the demand side.

The gas pipeline carries supply (production, storage, exports) and no demand at all.
Residential, commercial, industrial and electric-power deliveries complete the balance.
National only; state-level is deferred. See pipelines/eia/CLAUDE.md for live-confirmed codes.

No geo_map here, unlike pull_gas_capacity.py's sibling route -- confirmed live that
natural-gas/cons/sum resolves area-name to "US" cleanly for all four sectors, unlike
natural-gas/stor/cap and natural-gas/stor/wkly, which return the literal string "NA"."""

from __future__ import annotations

import pandas as pd
from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

# Named, never selected by index -- see this module's test.
RESIDENTIAL = "N3010US2"
COMMERCIAL = "N3020US2"
INDUSTRIAL = "N3035US2"
ELECTRIC_POWER = "N3045US2"

CONSUMPTION: list[str] = [RESIDENTIAL, COMMERCIAL, INDUSTRIAL, ELECTRIC_POWER]

CONSUMPTION_ROUTE = "natural-gas/cons/sum"
CONSUMPTION_FREQUENCY = "monthly"


def pull_consumption(client: EIAClient) -> pd.DataFrame:
    """One route's rows. Separate from main so a cassette test can exercise it directly."""
    return client.get_series(
        route=CONSUMPTION_ROUTE, series=CONSUMPTION, frequency=CONSUMPTION_FREQUENCY
    )


def main() -> None:
    with failure_scope("eia.pull_gas_consumption"):
        df = pull_consumption(EIAClient())
        # A sector that comes back with no rows at all (the whole pull failing, or one
        # of four sectors silently missing) must not be reported as success -- record it
        # so failure_scope's raise_if_any() fires on the way out. get_series always
        # builds the series_id column, even on an empty frame, so this is safe when
        # df is wholly empty too.
        for code in sorted(set(CONSUMPTION) - set(df["series_id"])):
            record_failure(code, RuntimeError("no rows returned"))
        if df.empty:
            print("no gas consumption rows pulled", flush=True)
            return
        write_ts_long(df, source="eia")
        print(f"wrote {len(df)} gas consumption rows", flush=True)


if __name__ == "__main__":
    main()
