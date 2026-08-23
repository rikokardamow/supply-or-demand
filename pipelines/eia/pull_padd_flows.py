"""Pull monthly inter-PADD crude oil movements (pipeline/tanker_barge/rail) into flows."""

from __future__ import annotations

import pandas as pd
from core.storage import write_flows

from pipelines.eia.client import EIAClient
from pipelines.eia.corridors import discover_all_corridors


def main() -> None:
    client = EIAClient()
    corridors_by_route = discover_all_corridors(client)

    frames = [
        client.get_flows(route=route, corridors=corridors, frequency="monthly")
        for route, corridors in corridors_by_route.items()
        if corridors
    ]
    df = pd.concat(frames, ignore_index=True)
    write_flows(df, source="eia")
    print(f"wrote {len(df)} rows across {len(corridors_by_route)} routes")


if __name__ == "__main__":
    main()
