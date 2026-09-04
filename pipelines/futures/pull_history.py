"""One-off backfill entrypoint. For IBKRClient: 1993-01-01 onward where the source allows.
For ManualCSVClient (this session's actual live path -- no IBKR Gateway running): reads
every settles_*.csv file already present under data/manual/futures/, whatever date range
that covers -- there is no API to backfill from, only whatever the operator has dropped in."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.futures.client import ROOTS, ContractMeta, get_client
from pipelines.futures.series_meta import ROLL_RULE, write_series_meta
from pipelines.futures.to_ts_long import settles_to_ts_long

HISTORY_START = date(1993, 1, 1)


def _series_meta_rows(contracts: list[ContractMeta], source: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "root": c.root,
                "contract": c.contract,
                "expiry": pd.Timestamp(c.expiry),
                "tick_size": c.tick_size,
                "contract_unit": c.contract_unit,
                "currency": c.currency,
                "roll_rule": ROLL_RULE,
                "source": source,
            }
            for c in contracts
        ]
    )


def main() -> None:
    from core.settings import settings

    client = get_client()
    ingested_at = pd.Timestamp(datetime.now())
    today = date.today()

    total_rows = 0
    for root in ROOTS:
        # Per-root failure isolation -- one root's own failure must never abort the rest,
        # same pattern pipelines/entsoe's own pull scripts use.
        try:
            contracts = client.list_contracts(root)
            if not contracts:
                print(f"{root}: no contracts found", flush=True)
                continue

            write_series_meta(_series_meta_rows(contracts, settings.futures_source))

            settles = client.get_settles(
                root, [c.contract for c in contracts], HISTORY_START, today
            )
            if settles.empty:
                print(f"{root}: no settles rows pulled", flush=True)
                continue

            long_rows = settles_to_ts_long(settles, ingested_at)
            write_ts_long(long_rows, source="futures")
            total_rows += len(long_rows)
            print(f"{root}: wrote {len(long_rows)} rows", flush=True)
        except Exception as exc:
            print(f"{root}: FAILED ({type(exc).__name__}: {exc})", flush=True)

    print(f"pull_history: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
