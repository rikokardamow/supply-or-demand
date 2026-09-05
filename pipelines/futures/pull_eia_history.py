"""Entrypoint: backfill real NYMEX futures settlements from EIA into the lake.

One-off / occasional history pull, deliberately **not** registered in
`infra/run_scheduled.py` -- the EIA futures route is discontinued (last observation
2024-04-05), so there is nothing new to fetch on a schedule. Re-run it only if the lake
is rebuilt.

See `pipelines/futures/eia_futures.py` for what this source does and does not give.
"""

from __future__ import annotations

from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.futures.eia_futures import EIA_FUTURES, ROUTE, eia_series_ids, rows_to_ts_long


def main() -> None:
    client = EIAClient()
    geo_map = {spec.eia_id: spec.geo for spec in EIA_FUTURES}

    # EIA's futures route never populates area-name, so pass geo explicitly -- the same
    # gotcha pipelines/eia/pull_gas_storage.py already hit on natural-gas/stor/wkly.
    raw = client.get_series(ROUTE, eia_series_ids(), "daily", geo_map=geo_map)
    print(f"eia futures: {len(raw)} raw rows for {len(eia_series_ids())} series", flush=True)

    rows = rows_to_ts_long(raw)
    if rows.empty:
        print("eia futures: nothing to write", flush=True)
        return

    write_ts_long(rows, source="eia")
    for series_id, group in rows.groupby("series_id"):
        print(
            f"  {series_id}: {len(group)} rows "
            f"{group['ts'].min().date()} -> {group['ts'].max().date()}",
            flush=True,
        )
    print(f"eia futures: wrote {len(rows)} rows", flush=True)


if __name__ == "__main__":
    main()
