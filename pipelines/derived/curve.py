"""Reads the futures settlement lake, computes nearby ranks/spreads/convexity/regime via
core/curve.py, and writes derived.spread.<root>.*/derived.curve.<root>.* series back.
Registered as a Spec 13 orchestration step (infra/run_scheduled.py's daily cadence group),
run after pipelines.futures.pull_daily -- not GitHub Actions, per the lake-on-laptop
decision. Per-root failure isolation, matching every other pipeline's own pull loop and
pipelines/futures/pull.py::pull_root."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from core import rights
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


def _settles_for(root: str, meta: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The root's series_meta rows and the lake's settle rows for its contracts."""
    root_meta = meta[meta["root"] == root]
    if root_meta.empty:
        return root_meta, pd.DataFrame()
    series_ids = [f"fut.{root}.{c}.settle" for c in root_meta["contract"].tolist()]
    return root_meta, read_ts_long(series_ids=series_ids)


def _panel_from(root_meta: pd.DataFrame, long_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    if root_meta.empty or long_df.empty:
        return pd.DataFrame(), pd.Series(dtype="datetime64[ns]")

    long_df = long_df.copy()
    long_df["contract"] = long_df["series_id"].str.split(".").str[2]
    contract_panel = long_df.pivot_table(index="ts", columns="contract", values="value")
    expiries = root_meta.set_index("contract")["expiry"]
    # Only contracts that actually have settle rows in the lake -- series_meta can list a
    # contract before any real settle data for it has landed.
    expiries = expiries.loc[expiries.index.intersection(contract_panel.columns)]
    return contract_panel, expiries


def contract_panel_for(root: str, meta: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Public (not module-private) so apps/dashboard/pages/18_curve.py can reuse this same
    settle-pivot logic directly, matching pipelines/eia/transforms.py's own
    "page imports a pipeline's transform helper" precedent."""
    return _panel_from(*_settles_for(root, meta))


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


def restricted_sources(long_df: pd.DataFrame) -> list[str]:
    """The class d sources among a settle frame's rows (`core.rights.SOURCE_CLASS`). A
    source the register does not know counts as restricted: no mapping means not read."""
    sources = sorted(set(long_df["source"].astype(str)))
    return [s for s in sources if rights.SOURCE_CLASS.get(s, "d") == "d"]


def pull_root(root: str, meta: pd.DataFrame, ingested_at: pd.Timestamp) -> int:
    root_meta, long_df = _settles_for(root, meta)
    contract_panel, expiries = _panel_from(root_meta, long_df)
    if contract_panel.empty or len(expiries) < 2:
        print(f"{root}: not enough contracts for a curve yet", flush=True)
        return 0

    # Every derived.spread.* / derived.curve.* row is written under source "derived",
    # which inherits its class from its inputs. Class d settles (a vendor export, IBKR)
    # must not become class b rows in that shared partition (RIGHTS.md).
    restricted = restricted_sources(long_df)
    if restricted:
        print(
            f"{root}: settles come from class d source(s) {restricted}; "
            "derived curve rows not written (RIGHTS.md)",
            flush=True,
        )
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
