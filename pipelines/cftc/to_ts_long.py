"""Wide CFTC disaggregated rows -> long ts_long rows. One column per metric becomes one
series_id -- cftc.<root>.mm_long / .mm_short / .prod_merc_long / .prod_merc_short / .oi."""

from __future__ import annotations

import pandas as pd

_METRIC_COLUMNS = ["mm_long", "mm_short", "prod_merc_long", "prod_merc_short", "oi"]


def disaggregated_to_ts_long(
    df: pd.DataFrame, root: str, revision_date: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )

    frames = []
    for metric in _METRIC_COLUMNS:
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"cftc.{root}.{metric}",
                    "source": "cftc",
                    "ts": df["date"],
                    "value": df[metric].astype(float),
                    "unit": "contracts",
                    "geo": root.upper(),
                    "freq": "W",
                    "revision_date": revision_date,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
