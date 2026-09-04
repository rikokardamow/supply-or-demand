"""Wide settles (date, root, contract, settle, oi, volume) -> long ts_long rows, one per
metric per row -- series_id fut.<root>.<contract>.settle / .oi / .volume, per
specs/00_TRADING_CONVENTIONS.md's naming convention."""

from __future__ import annotations

import pandas as pd

from pipelines.futures.client import load_contract_specs

_METRICS = ("settle", "oi", "volume")


def settles_to_ts_long(df: pd.DataFrame, revision_date: pd.Timestamp) -> pd.DataFrame:
    """`df` needs columns date, root, contract, settle, oi, volume (client.py's own
    get_settles() output shape). `oi` may be all-null (IBKRClient's own historical bars
    don't carry open interest) -- rows with a null value are dropped rather than written
    as a fake 0.0, matching the sanctions/Adanos precedent for "no data" vs "zero"."""
    currency_by_root = load_contract_specs().set_index("root")["currency"]

    frames = []
    for metric in _METRICS:
        metric_df = df[["date", "root", "contract", metric]].rename(columns={metric: "value"})
        metric_df = metric_df.dropna(subset=["value"])
        if metric_df.empty:
            continue
        unit = metric_df["root"].map(currency_by_root) if metric == "settle" else "contracts"
        series_id = (
            "fut." + metric_df["root"] + "." + metric_df["contract"] + f".{metric}"
        )
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "source": "futures",
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
