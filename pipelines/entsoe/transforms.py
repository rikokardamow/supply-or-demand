"""ENTSO-E-specific transforms built on core.storage output."""

from __future__ import annotations

import pandas as pd


def residual_load(load: pd.Series, wind: pd.Series, solar: pd.Series) -> pd.Series:
    """Load minus wind minus solar generation — what conventional (thermal/hydro/
    storage) capacity has to cover. All three series must be indexed by ts; missing
    wind/solar at a timestamp is treated as 0 (a zone can genuinely have no offshore
    wind, for instance), not dropped."""
    result: pd.Series = load - wind.reindex(load.index, fill_value=0.0) - solar.reindex(
        load.index, fill_value=0.0
    )
    return result


def net_position(flows_df: pd.DataFrame) -> pd.DataFrame:
    """Net export minus import per zone per timestamp, summed across every border that
    zone appears on. Positive = net exporter at that timestamp, negative = net
    importer. `flows_df` must have `ts`, `from_node`, `to_node`, `value` columns (the
    `flows` schema) — same logic as pipelines/eia/transforms.py's net_balance,
    generalised from PADD/month to zone/timestamp."""
    outbound = flows_df.groupby(["ts", "from_node"])["value"].sum().rename("outbound")
    inbound = flows_df.groupby(["ts", "to_node"])["value"].sum().rename("inbound")

    combined = pd.concat([outbound, inbound], axis=1).fillna(0.0)
    combined.index.names = ["ts", "zone"]
    combined = combined.reset_index()
    combined["net_position"] = combined["outbound"] - combined["inbound"]

    return combined[["ts", "zone", "net_position"]]
