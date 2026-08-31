"""Pure HDD/CDD functions -- both bases (18C EU / 65F US) stored explicitly in the
series_id per the spec's own instruction, since a bare "hdd.dublin" wouldn't say which
base/unit it's in."""

from __future__ import annotations

import pandas as pd


def celsius_to_fahrenheit(t_c: float) -> float:
    return t_c * 9 / 5 + 32


def hdd(t_mean: float, base: float) -> float:
    return max(0.0, base - t_mean)


def cdd(t_mean: float, base: float) -> float:
    return max(0.0, t_mean - base)


_BASE_VALUE = {"c18": 18.0, "f65": 65.0}


def to_ts_long(
    daily_df: pd.DataFrame, cities_df: pd.DataFrame, revision_date: pd.Timestamp
) -> pd.DataFrame:
    """`daily_df` needs columns city, ts, temp_mean_c (client.py's own output shape).
    `cities_df` needs columns city, base (EU cities "c18", US cities "f65" -- see
    pipelines/weather/cities.py). Returns ts_long rows for both hdd.<city>.<base> and
    cdd.<city>.<base>, geo=city, unit="degree-days", freq="D"."""
    merged = daily_df.merge(cities_df[["city", "base"]], on="city", how="left")
    if merged["base"].isna().any():
        missing = sorted(merged.loc[merged["base"].isna(), "city"].unique())
        raise ValueError(f"No base found in cities_df for: {missing}")

    is_us = merged["base"] == "f65"
    temp_f = merged["temp_mean_c"].map(celsius_to_fahrenheit)
    t_for_base = merged["temp_mean_c"].where(~is_us, temp_f)
    base_value = merged["base"].map(_BASE_VALUE)

    frames = []
    for metric_name, metric_fn in (("hdd", hdd), ("cdd", cdd)):
        value = [metric_fn(t, b) for t, b in zip(t_for_base, base_value, strict=True)]
        frames.append(
            pd.DataFrame(
                {
                    "series_id": metric_name + "." + merged["city"] + "." + merged["base"],
                    "source": "open_meteo",
                    "ts": merged["ts"],
                    "value": value,
                    "unit": "degree-days",
                    "geo": merged["city"],
                    "freq": "D",
                    "revision_date": revision_date,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
