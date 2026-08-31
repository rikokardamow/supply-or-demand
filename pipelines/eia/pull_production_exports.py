"""Pull monthly US dry natural gas production and LNG exports into ts_long. Feedgas
(gas consumed at LNG liquefaction facilities before export) has no distinct EIA API
series -- only the total export volume below is tracked. Documented as out of scope
here rather than faked, per the spec's own note (specs/05_us-gas-power.md)."""

from __future__ import annotations

import pandas as pd
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

PRODUCTION_SERIES = ["N9070US2"]  # U.S. Dry Natural Gas Production (MMcf)

# Confirmed live (Spec 05 Session C): this is the genuine, pre-aggregated national
# total -- NOT the spec's originally-named natural-gas/move/poe2 route, whose
# per-destination-country series only cover a small fraction of real exports (summed
# to ~88-103 Bcf/month vs. this series' ~503 Bcf/month for the same period). Cross-
# checked live: natural-gas/sum/lsum's own pipeline-exports series (N9132US2) plus
# this one equals that route's combined total-exports series (N9130US2) exactly.
# See pipelines/eia/NOTES.md for the full story.
LNG_EXPORTS_SERIES = ["N9133US2"]  # Liquefied U.S. Natural Gas Exports (MMcf)


def main() -> None:
    client = EIAClient()
    production = client.get_series("natural-gas/prod/sum", PRODUCTION_SERIES, "monthly")
    lng_exports = client.get_series("natural-gas/sum/lsum", LNG_EXPORTS_SERIES, "monthly")

    df = pd.concat([production, lng_exports], ignore_index=True)
    write_ts_long(df, source="eia")
    print(
        f"wrote {len(df)} rows ({len(production)} production, {len(lng_exports)} LNG exports)"
    )


if __name__ == "__main__":
    main()
