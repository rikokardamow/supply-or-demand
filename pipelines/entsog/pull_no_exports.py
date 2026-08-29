"""Session A acceptance script: pulls the NO_EXPORTS corridor's physical flow (last ~30
days) into flows, at point level (per specs/03_entsog-eu-gas-flows.md's data model —
corridor aggregation is a separate view, built in Session B, not baked into raw storage
here)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from core.storage import write_flows

from pipelines.entsog.client import ENTSOGClient
from pipelines.entsog.corridors import CORRIDORS, validate_corridors
from pipelines.entsog.directory import load_directory

KWH_TO_GWH = 1_000_000
LOOKBACK_DAYS = 30


def main() -> None:
    directory = load_directory()
    validate_corridors(directory)

    client = ENTSOGClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    frames = []
    for point in CORRIDORS["NO_EXPORTS"]:
        raw = client.get_physical_flow(point.point_key, point.direction_key, start, end)
        if raw.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "source": "entsog",
                    "from_node": point.from_node,
                    "to_node": point.to_node,
                    "value": raw["value_kwh_d"] / KWH_TO_GWH,
                    "unit": "GWh/d",
                    "ts": raw["ts"],
                    "mode": "pipeline",
                }
            )
        )

    df = pd.concat(frames, ignore_index=True)
    write_flows(df, source="entsog")
    print(f"wrote {len(df)} rows across {len(frames)} NO_EXPORTS points")


if __name__ == "__main__":
    main()
