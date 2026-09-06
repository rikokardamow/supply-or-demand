"""Pull 90 days of cross-border physical power flows for every mapped border into the
shared flows table (mode='power', per the spec's data model)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.storage import write_flows

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.zones import BORDERS

LOOKBACK_DAYS = 90


def pull_flows(
    client: ENTSOEClient, borders: list[tuple[str, str]], start: date, end: date
) -> pd.DataFrame:
    """Shared by main()'s full backfill and pull_daily.py's trailing-window re-pull —
    same per-border resilience (one flaky border must never abort the rest)."""
    frames = []
    failed_borders = []
    for zone_from, zone_to in borders:
        try:
            raw = client.get_crossborder_flow(zone_from, zone_to, start, end)
        except RuntimeError as exc:
            # One flaky border shouldn't abort the whole pull -- see pull_prices.py's
            # identical reasoning. Re-run to retry whatever failed.
            record_failure(f"{zone_from} -> {zone_to}", exc)
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

    if failed_borders:
        print(f"failed borders (re-run to retry): {failed_borders}", flush=True)
    if not frames:
        return pd.DataFrame(
            columns=["source", "from_node", "to_node", "value", "unit", "ts", "mode"]
        )
    return pd.concat(frames, ignore_index=True)


@fails_loudly("entsoe.pull_flows")
def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    df = pull_flows(client, BORDERS, start, end)
    if df.empty:
        print("no flow rows pulled", flush=True)
        return
    write_flows(df, source="entsoe")
    n_borders = df[["from_node", "to_node"]].drop_duplicates().shape[0]
    print(f"wrote {len(df)} rows across {n_borders} borders", flush=True)


if __name__ == "__main__":
    main()
