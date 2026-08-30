"""Daily incremental entrypoint for orchestration (Spec 13): day-ahead prices for the
newly published next day (ENTSO-E publishes ~12:45 CET per root NOTES.md's release
calendar) plus actuals — load, generation, wind/solar forecast, cross-border flows —
for the prior day. `pull_prices.py`/`pull_actuals.py`/`pull_flows.py`'s 90/14/90-day
pulls are one-off backfills; this is the actual scheduled entrypoint, reusing their
`pull_*()` helpers with narrower windows.

Day-ahead prices are auction-cleared and never revised (see pipelines/entsoe/NOTES.md's
revision_date note) and `write_ts_long` already keeps the latest-revision_date row per
(series_id, ts) — so re-pulling an overlapping window for prices/load/generation/
wind-solar-forecast is naturally idempotent with no extra logic needed, unlike
pipelines/entsog's 15-day revision window (ENTSOG's flows are actually re-revised).

Cross-border flows are the one exception: the `flows` schema (per core/schemas.py) has
no revision_date column, so plain full-row de-dup can't tell a revised value from a
distinct new row — same problem pipelines/entsog solved for its own daily re-pull.
`write_flows`'s `replace_window` (already added for that) is reused here unchanged."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from core.storage import write_flows, write_ts_long

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.pull_actuals import pull_actuals
from pipelines.entsoe.pull_flows import pull_flows
from pipelines.entsoe.pull_prices import pull_prices
from pipelines.entsoe.zones import BORDERS, ZONES

# Prices for day D+1 publish ~12:45 CET on day D — pull from yesterday through
# tomorrow so a run at any time of day (before or after publication) both picks up
# whatever's newly available and re-confirms yesterday's/today's figures, with a
# one-day safety margin either side against a run that's early or late.
PRICE_START_OFFSET_DAYS = 1
PRICE_END_OFFSET_DAYS = 2

# Actuals for the prior day only — per the spec's own Session D scope.
ACTUALS_LOOKBACK_DAYS = 1


def main() -> None:
    client = ENTSOEClient()
    today = date.today()

    price_start = today - timedelta(days=PRICE_START_OFFSET_DAYS)
    price_end = today + timedelta(days=PRICE_END_OFFSET_DAYS)
    prices = pull_prices(client, ZONES, price_start, price_end)
    if prices.empty:
        print("no price rows pulled", flush=True)
    else:
        write_ts_long(prices, source="entsoe")
        print(f"wrote {len(prices)} price rows", flush=True)

    actuals_start = today - timedelta(days=ACTUALS_LOOKBACK_DAYS)
    actuals_end = today
    actuals = pull_actuals(client, ZONES, actuals_start, actuals_end)
    for label, df in actuals.items():
        if df.empty:
            print(f"no {label} rows pulled", flush=True)
            continue
        write_ts_long(df, source="entsoe")
        print(f"wrote {len(df)} {label} rows", flush=True)

    flows = pull_flows(client, BORDERS, actuals_start, actuals_end)
    if flows.empty:
        print("no flow rows pulled", flush=True)
    else:
        replace_window = (pd.Timestamp(actuals_start), pd.Timestamp(actuals_end))
        write_flows(flows, source="entsoe", replace_window=replace_window)
        print(f"wrote {len(flows)} flow rows", flush=True)


if __name__ == "__main__":
    main()
