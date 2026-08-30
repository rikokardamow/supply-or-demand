"""Pull 90 days of cross-border physical power flows for every mapped border into the
shared flows table (mode='power', per the spec's data model)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from core.storage import write_flows

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.zones import BORDERS

LOOKBACK_DAYS = 90


def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    frames = []
    failed_borders = []
    for zone_from, zone_to in BORDERS:
        try:
            raw = client.get_crossborder_flow(zone_from, zone_to, start, end)
        except RuntimeError as exc:
            # One flaky border shouldn't abort the whole pull -- see pull_prices.py's
            # identical reasoning. Re-run to retry whatever failed.
            print(f"{zone_from} -> {zone_to}: FAILED ({exc}) — skipping", flush=True)
            failed_borders.append((zone_from, zone_to))
            continue
        print(f"{zone_from} -> {zone_to}: {len(raw)} rows", flush=True)
        if raw.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "source": "entsoe",
                    "from_node": zone_from,
                    "to_node": zone_to,
                    "value": raw["value"],
                    "unit": "MW",
                    "ts": raw["ts"],
                    "mode": "power",
                }
            )
        )

    if not frames:
        print("no flow rows pulled", flush=True)
        return
    df = pd.concat(frames, ignore_index=True)
    write_flows(df, source="entsoe")
    print(f"wrote {len(df)} rows across {len(BORDERS) - len(failed_borders)} borders", flush=True)
    if failed_borders:
        print(f"failed borders (re-run to retry): {failed_borders}", flush=True)


if __name__ == "__main__":
    main()
