"""Population-weighted EU/US HDD or CDD aggregates -- series_id `hdd.eu.popw` /
`hdd.us.popw` per the spec's own example. Region is derived from each city's base (every
EU city in cities.csv uses "c18", every US city "f65") rather than a separate region
column -- a deliberate simplification since the two coincide exactly in this dataset;
revisit if a future non-EU/US city with a c18/f65 base is ever added."""

from __future__ import annotations

from typing import Literal

import pandas as pd

_REGION_BY_BASE = {"c18": "eu", "f65": "us"}


def population_weighted(
    long_df: pd.DataFrame,
    cities_df: pd.DataFrame,
    metric: Literal["hdd", "cdd"],
    revision_date: pd.Timestamp,
) -> pd.DataFrame:
    prefix = f"{metric}."
    rows = long_df[long_df["series_id"].str.startswith(prefix)].copy()
    if rows.empty:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )

    parts = rows["series_id"].str.split(".")
    rows["city"] = parts.str[1:-1].str.join(".")
    rows = rows.merge(cities_df[["city", "population_weight", "base"]], on="city", how="left")
    if rows["population_weight"].isna().any():
        missing = sorted(rows.loc[rows["population_weight"].isna(), "city"].unique())
        raise ValueError(f"No population_weight found in cities_df for: {missing}")

    rows["region"] = rows["base"].map(_REGION_BY_BASE)
    rows["weighted"] = rows["value"] * rows["population_weight"]
    grouped = rows.groupby(["region", "ts"])["weighted"].sum().reset_index()

    return pd.DataFrame(
        {
            "series_id": metric + "." + grouped["region"] + ".popw",
            "source": "open_meteo",
            "ts": grouped["ts"],
            "value": grouped["weighted"],
            "unit": "degree-days",
            "geo": grouped["region"].str.upper(),
            "freq": "D",
            "revision_date": revision_date,
        }
    )
