"""Pull weekly Lower-48 + regional natural gas working storage into ts_long. See
pipelines/eia/CLAUDE.md for the confirmed series codes and the area-name="NA" quirk this
route has (geo comes from an explicit map, not EIAClient's usual area-name normalisation).

These volumes are Bcf, while its sibling pull_gas_capacity.py publishes capacity in MMcf
(a factor of 1,000) -- see that module's fullness_pct for the presentation-time conversion."""

from __future__ import annotations

from core.storage import write_ts_long

from pipelines.eia.client import EIAClient

STORAGE_GEO_MAP = {
    "NW2_EPG0_SWO_R48_BCF": "L48",
    "NW2_EPG0_SWO_R31_BCF": "East",
    "NW2_EPG0_SWO_R32_BCF": "Midwest",
    "NW2_EPG0_SWO_R33_BCF": "SouthCentral",
    "NW2_EPG0_SSO_R33_BCF": "SouthCentral_Salt",
    "NW2_EPG0_SNO_R33_BCF": "SouthCentral_Nonsalt",
    "NW2_EPG0_SWO_R34_BCF": "Mountain",
    "NW2_EPG0_SWO_R35_BCF": "Pacific",
}


def main() -> None:
    client = EIAClient()
    df = client.get_series(
        route="natural-gas/stor/wkly",
        series=list(STORAGE_GEO_MAP),
        frequency="weekly",
        geo_map=STORAGE_GEO_MAP,
    )
    write_ts_long(df, source="eia")
    print(f"wrote {len(df)} rows across {df['geo'].nunique()} regions")


if __name__ == "__main__":
    main()
