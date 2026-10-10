"""Reads the futures settlement lake, computes nearby ranks/spreads/convexity/regime via
core/curve.py, and writes derived.spread.<root>.*/derived.curve.<root>.* series back.
Registered as a Spec 13 orchestration step (infra/run_scheduled.py's daily cadence group),
run after pipelines.futures.pull_daily -- not GitHub Actions, per the lake-on-laptop
decision. Per-root failure isolation, matching every other pipeline's own pull loop and
pipelines/futures/pull.py::pull_root."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, overload

import pandas as pd
from core.curve import (
    REGIME_CODES,
    convexity,
    curve_regime,
    dec_dec,
    nearby_panel,
    time_spreads,
)
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

from pipelines.futures.client import ROOTS
from pipelines.futures.series_meta import read_series_meta

_SPREAD_COLUMNS = ("s12", "s13", "s16", "s1_12", "s23")


_METRICS_BY_PREFERENCE: Final[tuple[str, ...]] = ("settle", "close")
"""Settle first: an exchange settlement is the better number where one exists. `.close` is
last-trade data, from sources like the IBKR MCP connector -- see
pipelines/futures/CLAUDE.md for the measured difference between the two."""


@overload
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: Literal[False] = False
) -> tuple[pd.DataFrame, pd.Series]: ...
@overload
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: Literal[True]
) -> tuple[pd.DataFrame, pd.Series, dict[str, str]]: ...
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: bool = False
) -> tuple[pd.DataFrame, pd.Series] | tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    """Public (not module-private) so apps/dashboard/pages/18_curve.py can reuse this same
    pivot logic directly, matching pipelines/eia/transforms.py's own "page imports a
    pipeline's transform helper" precedent.

    Reads both `.settle` and `.close` and picks ONE metric per contract -- settle if that
    contract has any settle rows, close otherwise. Per contract, never per row: a settlement
    and a last trade are different quantities, and blending them inside one column would
    leave every spread downstream measuring something nobody chose.
    """
    root_meta = meta[meta["root"] == root]
    empty: tuple[pd.DataFrame, pd.Series] = (
        pd.DataFrame(),
        pd.Series(dtype="datetime64[ns]"),
    )
    if root_meta.empty:
        return (*empty, {}) if return_provenance else empty

    contracts = root_meta["contract"].tolist()
    series_ids = [
        f"fut.{root}.{contract}.{metric}"
        for contract in contracts
        for metric in _METRICS_BY_PREFERENCE
    ]
    long_df = read_ts_long(series_ids=series_ids)
    if long_df.empty:
        return (*empty, {}) if return_provenance else empty

    long_df = long_df.copy()
    parts = long_df["series_id"].str.split(".")
    long_df["contract"] = parts.str[2]
    long_df["metric"] = parts.str[3]

    available = long_df.groupby("contract")["metric"].agg(set)
    chosen: dict[str, str] = {
        str(contract): next(m for m in _METRICS_BY_PREFERENCE if m in metrics)
        for contract, metrics in available.items()
    }
    picked = long_df[
        [chosen.get(c) == m for c, m in zip(long_df["contract"], long_df["metric"], strict=True)]
    ]

    contract_panel = picked.pivot_table(index="ts", columns="contract", values="value")
    expiries = root_meta.set_index("contract")["expiry"]
    # Only contracts that actually have rows in the lake -- series_meta can list a contract
    # before any real price data for it has landed.
    expiries = expiries.loc[expiries.index.intersection(contract_panel.columns)]
    if return_provenance:
        return contract_panel, expiries, chosen
    return contract_panel, expiries


def _write_derived(
    root: str, series_id_suffix: str, values: pd.Series, ingested_at: pd.Timestamp
) -> int:
    values = values.dropna()
    if values.empty:
        return 0
    df = pd.DataFrame(
        {
            "series_id": f"derived.{series_id_suffix}",
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype=float),
            "unit": "USD",
            "geo": root.upper(),
            "freq": "D",
            "revision_date": ingested_at,
        }
    )
    write_ts_long(df, source="derived")
    return len(df)


def pull_root(root: str, meta: pd.DataFrame, ingested_at: pd.Timestamp) -> int:
    contract_panel, expiries = contract_panel_for(root, meta)
    if contract_panel.empty or len(expiries) < 2:
        print(f"{root}: not enough contracts for a curve yet", flush=True)
        return 0

    _adjusted, unadj, _roll_dates = nearby_panel(contract_panel, expiries)
    spreads = time_spreads(unadj)
    cv123 = convexity(unadj)
    regime = curve_regime(unadj)
    decs = dec_dec(contract_panel)

    total = 0
    for col in _SPREAD_COLUMNS:
        total += _write_derived(root, f"spread.{root}.{col}", spreads[col], ingested_at)
    for col in decs.columns:
        total += _write_derived(root, f"spread.{root}.{col}", decs[col], ingested_at)
    total += _write_derived(root, f"curve.{root}.cv123", cv123, ingested_at)

    regime_codes = regime["state"].map(REGIME_CODES).astype(float)
    total += _write_derived(root, f"curve.{root}.regime", regime_codes, ingested_at)

    print(f"{root}: wrote {total} derived rows", flush=True)
    return total


@fails_loudly("derived.curve")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    meta = read_series_meta()

    total_rows = 0
    for root in ROOTS:
        try:
            total_rows += pull_root(root, meta, ingested_at)
        except Exception as exc:
            record_failure(f"{root}", exc)

    print(f"derived.curve: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
