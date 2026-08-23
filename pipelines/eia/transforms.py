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
