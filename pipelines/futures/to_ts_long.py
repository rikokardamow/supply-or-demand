"""Wide settles (date, root, contract, settle, oi, volume) -> long ts_long rows, one per
metric per row -- series_id fut.<root>.<contract>.settle / .oi / .volume, per
specs/00_TRADING_CONVENTIONS.md's naming convention.

`source` is NOT hardcoded here -- the caller (pull.py) passes whatever
settings.futures_source actually produced this data ("ibkr"/"manual") through to
core.storage.write_ts_long's own `source` parameter, matching series_meta.py's
already-provider-aware pattern. Two different providers writing the *same*
series_id (e.g. a manual-CSV fallback and a later real IBKR pull both writing
fut.cl.z26.settle) are physically partitioned by source and coexist rather than
silently overwriting each other -- hardcoding one literal source string here would
break that the moment FUTURES_SOURCE is ever switched."""

from __future__ import annotations

import pandas as pd

from pipelines.futures.client import ContractMeta

_METRICS = ("settle", "oi", "volume")


def settles_to_ts_long(
    df: pd.DataFrame,
    revision_date: pd.Timestamp,
    contracts: list[ContractMeta],
    source: str,
) -> pd.DataFrame:
    """`df` needs columns date, root, contract, settle, oi, volume (client.py's own
    get_settles() output shape). `contracts` is the same list the caller already got
    from list_contracts() for this root -- reused here for currency/contract_unit
    instead of re-reading contract_specs.csv a second time. `source` must be the real
    provider ("ibkr"/"manual", i.e. settings.futures_source) -- passed explicitly
    rather than hardcoded, so this function can never silently mislabel which
    provider a row actually came from (the exact gotcha pipelines/weather/
    degree_days.py's own hardcoded source column hit earlier this project). `oi` may
    be all-null (IBKRClient's own historical bars don't carry open interest) -- rows
    with a null value are dropped rather than written as a fake 0.0, matching the
    sanctions/Adanos precedent for "no data" vs "zero"."""
    unit_by_key = {(c.root, c.contract): f"{c.currency}/{c.contract_unit}" for c in contracts}

    frames = []
    for metric in _METRICS:
        metric_df = df[["date", "root", "contract", metric]].rename(columns={metric: "value"})
        metric_df = metric_df.dropna(subset=["value"])
        if metric_df.empty:
            continue
        unit: list[str] | str
        if metric == "settle":
            keys = zip(metric_df["root"], metric_df["contract"], strict=True)
            unit = [unit_by_key.get(key, "unknown") for key in keys]
        else:
            unit = "contracts"
        series_id = "fut." + metric_df["root"] + "." + metric_df["contract"] + f".{metric}"
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "source": source,
                    "ts": metric_df["date"],
                    "value": metric_df["value"],
                    "unit": unit,
                    "geo": metric_df["root"].str.upper(),
                    "freq": "D",
                    "revision_date": revision_date,
                }
            )
        )

    if not frames:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )
    return pd.concat(frames, ignore_index=True)
