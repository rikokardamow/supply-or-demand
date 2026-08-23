"""EIA-specific transforms built on core.storage output. Seasonal maths belongs in
core.seasonal, not here — this module is for WPSR-specific derived metrics only."""

from __future__ import annotations

import pandas as pd


def days_of_cover(stocks: pd.Series, product_supplied: pd.Series) -> pd.Series:
    """Stocks divided by the trailing 4-week average of product supplied. Both series
    must be weekly-frequency and indexed by ts."""
    avg_product_supplied = product_supplied.rolling(4).mean()
    result: pd.Series = stocks / avg_product_supplied
    return result


def wpsr_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per metric (stocks, gross inputs/runs, utilisation, product supplied,
    imports), with the latest value, prior-week value, and week-over-week delta for
    each `series_id` present in `df`. Feeds the formatted WPSR table added in Session C."""
    latest_two = (
        df.sort_values("ts")
        .groupby("series_id")
        .tail(2)
        .sort_values(["series_id", "ts"])
    )

    rows = []
    for series_id, group in latest_two.groupby("series_id"):
        if len(group) < 2:
            continue
        prior, latest = group.iloc[-2], group.iloc[-1]
        rows.append(
            {
                "series_id": series_id,
                "latest_ts": latest["ts"],
                "latest_value": latest["value"],
                "prior_value": prior["value"],
                "delta": latest["value"] - prior["value"],
            }
        )

    return pd.DataFrame(rows)


def net_balance(flows_df: pd.DataFrame) -> pd.DataFrame:
    """Net inbound minus outbound crude volume per PADD per month, summed across all
    modes. Positive = net receiver that month, negative = net sender. `flows_df` must
    have `ts`, `from_node`, `to_node`, `value` columns (the `flows` schema)."""
    inbound = flows_df.groupby(["ts", "to_node"])["value"].sum().rename("inbound")
    outbound = flows_df.groupby(["ts", "from_node"])["value"].sum().rename("outbound")

    combined = pd.concat([inbound, outbound], axis=1).fillna(0.0)
    combined.index.names = ["ts", "padd"]
    combined = combined.reset_index()
    combined["net_balance"] = combined["inbound"] - combined["outbound"]

    return combined[["ts", "padd", "net_balance"]]
