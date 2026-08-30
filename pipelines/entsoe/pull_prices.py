"""Pull 90 days of day-ahead prices for the Session A zone list into ts_long."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.storage import write_ts_long

from pipelines.entsoe.client import ENTSOEClient

ZONES = ["DE_LU", "FR", "NL", "IE_SEM"]
LOOKBACK_DAYS = 90


def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    pulled_at = datetime.now(UTC)

    frames = []
    for zone in ZONES:
        raw = client.get_day_ahead_prices(zone, start, end)
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

    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="entsoe")
    print(f"wrote {len(df)} rows across {len(ZONES)} zones", flush=True)


if __name__ == "__main__":
    main()
