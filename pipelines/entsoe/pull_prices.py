"""Pull 90 days of day-ahead prices for all 13 covered zones into ts_long."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.storage import write_ts_long

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.zones import ZONES

LOOKBACK_DAYS = 90


def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    pulled_at = datetime.now(UTC)

    frames = []
    failed_zones = []
    for zone in ZONES:
        try:
            raw = client.get_day_ahead_prices(zone, start, end)
        except RuntimeError as exc:
            # ENTSOEClient already sanitises this to a bare status/type message (never
            # the raw exception — see client.py's leak-prevention rule) — one flaky
            # zone shouldn't abort an otherwise-successful 13-zone pull; re-run later
            # to pick up whatever failed.
            print(f"{zone}: FAILED ({exc}) — skipping", flush=True)
            failed_zones.append(zone)
            continue
        print(f"{zone}: {len(raw)} rows", flush=True)
        if raw.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"entsoe.{zone}.day_ahead_price",
                    "source": "entsoe",
                    "ts": raw["ts"],
                    "value": raw["value"],
                    "unit": "EUR/MWh",
                    "geo": zone,
                    "freq": raw["freq"],
                    "revision_date": pulled_at,
                }
            )
        )

    if not frames:
        print("no price rows pulled", flush=True)
        return
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="entsoe")
    print(f"wrote {len(df)} rows across {len(ZONES) - len(failed_zones)} zones", flush=True)
    if failed_zones:
        print(f"failed zones (re-run to retry): {failed_zones}", flush=True)


if __name__ == "__main__":
    main()
