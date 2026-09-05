"""Daily systematic positions: reads the lake, runs `core/strategies.py`, writes
`derived.pos.<strategy>.<root>` (Spec 21 Session B).

A strategy whose required ranks are absent is **skipped with a reason**, never written as
a flat series. Writing zeros would be the worst outcome available: a flat position is a
real trading decision, and storing one because data was missing would silently corrupt
every downstream attribution. The skips and their reasons are printed on every run and
returned by `rows_for_root` so the page can display them.

On the lake's current futures data (EIA ranks 1-4) that means `CARRY_1_13` (needs rank 13)
and `FWD_SPREAD_MR` (needs rank 7) are always skipped.

**The same discipline applies to the adjusted front month.** `derived.curve.<root>.f01_adj`
(written by `pipelines/derived/curve_ranks.py`, on the same `weekly_fri` cadence just before
this module) can legitimately be absent -- that pipeline can fail for one root while the raw
settle legs it doesn't touch still exist. `inputs_for_root` leaves `f01_adj` all-NaN rather
than silently substituting the raw `f01` rank: `core/systematic.py` is explicit that a raw
rank series scores the roll step as momentum, so a substitution would write a full set of
wrong `derived.pos.*` rows indistinguishable from a correct run. `rows_for_root` then reports
every "outright" strategy (the ones that actually consume `f01_adj`) as skipped with a
reason, rather than letting them quietly compute an all-NaN position and vanish from the
written frame with no trace. "spread" strategies (`CONVEX_SPREAD`, `SHORT_SPREAD_STATIC`,
`FWD_SPREAD_MR`) trade the unadjusted rank spread directly and never touch `f01_adj`, so a
missing adjusted series does not take them down too.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from core.storage import read_ts_long, write_ts_long
from core.strategies import (
    REGISTRY,
    StrategyInputs,
    available_strategies,
    build_positions,
    missing_ranks,
)

from pipelines.derived.curve_ranks import ADJUSTED_SUFFIX, RANK_ROOTS, RANKS

POSITION_ROOTS = RANK_ROOTS
UTIL_SERIES = "derived.cushing.util_decile"
UNIT = "position"


def _cot_series(root: str) -> str:
    return f"derived.cot.{root}.mm_pct_3y"


def read_legs() -> pd.DataFrame:
    wanted = [f"fut.{r}.{rank}.settle" for r in POSITION_ROOTS for rank in RANKS]
    wanted += [f"derived.curve.{r}.{ADJUSTED_SUFFIX}" for r in POSITION_ROOTS]
    wanted += [_cot_series(r) for r in POSITION_ROOTS]
    wanted.append(UTIL_SERIES)
    return read_ts_long(series_ids=wanted)


def _wide(long_df: pd.DataFrame, series_ids: list[str]) -> pd.DataFrame:
    rows = long_df[long_df["series_id"].isin(series_ids)]
    if rows.empty:
        return pd.DataFrame()
    return rows.pivot_table(index="ts", columns="series_id", values="value")


def inputs_for_root(long_df: pd.DataFrame, root: str) -> StrategyInputs | None:
    """Assemble every leg the registry can draw on for one root, or None if the root has
    no rank data at all."""
    rank_ids = [f"fut.{root}.{rank}.settle" for rank in RANKS]
    panel = _wide(long_df, rank_ids)
    if panel.empty:
        return None
    panel.columns = [str(c).split(".")[2] for c in panel.columns]
    panel = panel[[r for r in RANKS if r in panel.columns]].sort_index()

    adjusted = _wide(long_df, [f"derived.curve.{root}.{ADJUSTED_SUFFIX}"])
    f01_adj = (
        adjusted.iloc[:, 0].reindex(panel.index)
        if not adjusted.empty
        # Never substitute the raw rank: a roll step would then be scored as momentum.
        # `rows_for_root` reports every strategy that actually needs this as skipped.
        else pd.Series(np.nan, index=panel.index, dtype="float64")
    )

    util = _wide(long_df, [UTIL_SERIES])
    cot = _wide(long_df, [_cot_series(root)])
    return StrategyInputs(
        unadj=panel,
        f01_adj=f01_adj,
        util_decile=util.iloc[:, 0].reindex(panel.index).ffill() if not util.empty else None,
        cot_pct=cot.iloc[:, 0].reindex(panel.index).ffill() if not cot.empty else None,
    )


def position_rows(
    strategy: str, root: str, pos: pd.Series, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """One strategy's positions -> `ts_long` rows at `derived.pos.<strategy>.<root>`."""
    pos = pos.dropna()
    if pos.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "series_id": f"derived.pos.{strategy}.{root}",
            "source": "derived",
            "ts": pos.index,
            "value": pos.to_numpy(dtype="float64"),
            "unit": UNIT,
            "geo": "US",
            "freq": "D",
            "revision_date": ingested_at,
        }
    )


def rows_for_root(
    long_df: pd.DataFrame, root: str, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Positions for every runnable strategy, plus `{strategy: reason}` for the skips."""
    data = inputs_for_root(long_df, root)
    if data is None:
        return pd.DataFrame(), {}

    runnable = set(available_strategies(data.unadj))
    skipped = {
        name: (
            f"needs rank(s) {', '.join(f'f{r:02d}' for r in missing_ranks(strategy, data.unadj))}"
            f" -- {strategy.note}"
        )
        for name, strategy in REGISTRY.items()
        if name not in runnable
    }

    # `f01_adj` is left all-NaN by `inputs_for_root` when derived.curve.<root>.f01_adj is
    # absent, rather than silently substituted with the raw rank. Every "outright" strategy
    # consumes it (directly, or through vol_target/log_price); "spread" strategies trade the
    # unadjusted rank spread and never touch it. Report the affected strategies as skipped
    # here, before attempting to build them, so they never quietly compute an all-NaN
    # position and vanish from the written frame with no trace.
    if data.f01_adj.isna().all():
        for name in list(runnable):
            if REGISTRY[name].traded == "outright":
                skipped[name] = (
                    f"derived.curve.{root}.{ADJUSTED_SUFFIX} is absent from the lake -- "
                    "an outright strategy on the raw rank would score the roll step as "
                    "momentum, so it is skipped rather than run on the wrong input"
                )
                runnable.discard(name)

    frames = []
    for name in runnable:
        try:
            frames.append(position_rows(name, root, build_positions(name, data), ingested_at))
        except KeyError as exc:
            skipped[name] = f"{type(exc).__name__}: {exc}"

    frames = [f for f in frames if not f.empty]
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), skipped


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    long_df = read_legs()
    if long_df.empty:
        print("derived.pos: no futures legs in the lake", flush=True)
        return

    total = 0
    for root in POSITION_ROOTS:
        rows, skipped = rows_for_root(long_df, root, ingested_at)
        if rows.empty and not skipped:
            print(f"{root}: no rank data", flush=True)
            continue
        if not rows.empty:
            write_ts_long(rows, source="derived")
            total += len(rows)
            print(
                f"{root}: wrote {len(rows)} rows across "
                f"{rows['series_id'].nunique()} strategies",
                flush=True,
            )
        for name, reason in sorted(skipped.items()):
            print(f"  {root}/{name}: SKIPPED -- {reason}", flush=True)

    print(f"derived.pos: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
